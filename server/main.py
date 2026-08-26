import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from server.config import MOVE_SPEED, PORT, TICK_RATE
from server.db.database import Database
from server.game.avatar import validate_avatar
from server.game.chat import create_message, filter_messages_for_user
from server.game.combat import (
    ATTACK_TYPES, STUN_DURATION_MS,
    apply_hit, can_attack, calculate_damage, is_in_range, regen_stamina,
)
from server.game.ai_bot import AIBot, BOT_ID, BOT_AVATAR
from server.game.movement import move_by_direction, move_toward
from server.game.room import Room
from server.game.rooms_registry import RoomsRegistry

DIST_DIR = Path(__file__).resolve().parent.parent / "dist"

sio     = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
db      = Database()
rooms   = RoomsRegistry()
ai_bot  = AIBot()
_game_loop_task: asyncio.Task | None = None


def player_payload(player: dict) -> dict:
    now_ms = time.time() * 1000
    return {
        "id":           player["id"],
        "avatar":       player["avatar"],
        "position":     player["position"],
        "actionState":  player.get("actionState"),
        "stamina":      round(player.get("stamina", 100)),
        "blocking":     player.get("blocking", False),
        "stunned":      now_ms < player.get("stunnedUntil", 0),
        "stunnedUntil": player.get("stunnedUntil", 0),
        "tile":         player.get("tile", {"x": 0, "y": 0}),
    }


def room_channel(room_id: str) -> str:
    return f"room:{room_id}"


def all_players_payload(room_id: str) -> list[dict]:
    room = rooms.get_room(room_id)
    if not room:
        return []
    return [player_payload(p) for p in room.get_all_players()]


async def broadcast_room_state(room_id: str) -> None:
    await sio.emit("room:state", {"players": all_players_payload(room_id)}, room=room_channel(room_id))


async def broadcast_bubbles(room_id: str) -> None:
    room = rooms.get_room(room_id)
    if not room:
        return
    for player in room.get_all_players():
        bubbles = room.get_active_bubbles(player["id"])
        await sio.emit("chat:bubbles", bubbles, room=player["id"])


def apply_player_movement(room: Room, room_id: str, player: dict, now_ms: float) -> bool:
    """Apply direction or click-target movement (and tile transitions) for a
    single player. Returns True if the player's position/tile changed this tick.

    This must run for every player in the room, including the AI bot: only
    stamina regeneration is bot-exempt, not movement processing.
    """
    direction = player.get("direction", {"x": 0, "y": 0})
    if direction["x"] != 0 or direction["y"] != 0:
        new_pos = move_by_direction(player["position"], direction, MOVE_SPEED)
        transition = rooms.transition_player_tile_if_needed(player["id"], room_id, new_pos)
        if transition:
            player["tile"] = transition["tile"]
            room.update_player_position(player["id"], transition["position"])
        else:
            room.update_player_position(player["id"], new_pos)
        return True

    target = player.get("targetPosition")
    if target:
        new_pos = move_toward(player["position"], target, MOVE_SPEED)
        transition = rooms.transition_player_tile_if_needed(player["id"], room_id, new_pos)
        if transition:
            player["tile"] = transition["tile"]
            room.update_player_position(player["id"], transition["position"])
            player["targetPosition"] = None
            if player.get("pendingAction") is not None:
                player["actionState"] = player["pendingAction"]
                player["pendingAction"] = None
            return True

        room.update_player_position(player["id"], new_pos)
        if new_pos["x"] == target["x"] and new_pos["y"] == target["y"]:
            player["targetPosition"] = None
            if player.get("pendingAction") is not None:
                player["actionState"] = player["pendingAction"]
                player["pendingAction"] = None
        return True

    return False


async def game_loop() -> None:
    interval  = 1.0 / TICK_RATE
    last_time = time.time()
    while True:
        await asyncio.sleep(interval)
        now      = time.time()
        now_ms   = now * 1000
        delta_ms = (now - last_time) * 1000
        last_time = now
        moved_by_room: dict[str, bool] = {}

        for room_id, room in rooms.rooms.items():
            moved = False
            for player in room.get_all_players():
                # Regen stamina for everyone except AI bot (managed by its own tick)
                if player["id"] != BOT_ID:
                    player["stamina"] = regen_stamina(player.get("stamina", 100), delta_ms)

                # Skip movement while stunned
                if now_ms < player.get("stunnedUntil", 0):
                    continue

                if apply_player_movement(room, room_id, player, now_ms):
                    moved = True

            moved_by_room[room_id] = moved

        # ── AI bot tick (lobby only) ─────────────────────────────────────────
        lobby = rooms.get_room("lobby")
        if lobby:
            all_players = lobby.get_all_players()
            bot_attack = ai_bot.tick(now, all_players)

            if bot_attack:
                target_player = lobby.get_player(bot_attack["targetId"])
                if target_player:
                    new_stamina = apply_hit(target_player.get("stamina", 100), bot_attack["damage"])
                    target_player["stamina"] = new_stamina
                    stun_until = 0.0
                    if new_stamina <= 0:
                        stun_until = now_ms + STUN_DURATION_MS
                        target_player["stunnedUntil"] = stun_until
                    await sio.emit("combat:hit", {
                        "attackerId": BOT_ID,
                        "targetId": bot_attack["targetId"],
                        "type": bot_attack["type"],
                        "damage": bot_attack["damage"],
                        "blocked": bot_attack["blocked"],
                        "targetStamina": round(new_stamina),
                        "stunnedUntil": stun_until,
                    }, room=room_channel("lobby"))
                    moved_by_room["lobby"] = True

            # ── AI chat (lobby only) ────────────────────────────────────────
            if ai_bot.pending_chat:
                msg = create_message(
                    sender_id=BOT_ID,
                    sender_name=BOT_AVATAR["username"],
                    text=ai_bot.pending_chat,
                    type="public",
                )
                lobby.add_message(msg)
                await sio.emit("chat:message", msg, room=room_channel("lobby"))
                ai_bot.pending_chat = None

        for room_id, moved in moved_by_room.items():
            if moved:
                await broadcast_room_state(room_id)
            await broadcast_bubbles(room_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _game_loop_task
    await db.connect()
    # Spawn AI fighter on the right side of the lounge
    lobby = rooms.get_room("lobby")
    assert lobby is not None
    bot = lobby.add_player(BOT_ID, BOT_AVATAR)
    bot['position'] = {'x': 620.0, 'y': 400.0}
    _game_loop_task = asyncio.create_task(game_loop())
    yield
    if _game_loop_task:
        _game_loop_task.cancel()
        try:
            await _game_loop_task
        except asyncio.CancelledError:
            pass
    await db.disconnect()


app = FastAPI(lifespan=lifespan)

if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path:
            file_path = DIST_DIR / full_path
            if file_path.is_file():
                return FileResponse(file_path)
        return FileResponse(DIST_DIR / "index.html")


@sio.event
async def connect(sid, environ):
    await sio.enter_room(sid, sid)


@sio.event
async def disconnect(sid):
    current_room_id = rooms.get_player_room_id(sid)
    rooms.leave_current_room(sid)
    if current_room_id:
        await sio.emit("player:left", {"id": sid}, room=room_channel(current_room_id))
        await broadcast_room_state(current_room_id)
        await sio.emit("room:list:changed", {})


@sio.on("player:join")
async def player_join(sid, data):
    avatar = data.get("avatar", {})
    if not validate_avatar(avatar):
        await sio.emit("error", {"message": "Invalid avatar configuration"}, room=sid)
        return

    await db.save_avatar(avatar)
    player = rooms.join_room(sid, avatar, "lobby")
    if not player:
        await sio.emit("error", {"message": "Failed to join lobby"}, room=sid)
        return

    lobby = rooms.get_room("lobby")
    assert lobby is not None
    await sio.enter_room(sid, room_channel("lobby"))

    await sio.emit(
        "player:joined",
        {
            "id": sid,
            "avatar": avatar,
            "position": player["position"],
            "tile": player.get("tile", {"x": 0, "y": 0}),
        },
        room=sid,
    )
    await sio.emit("room:state", {"players": all_players_payload("lobby")}, room=sid)

    db_messages = await db.get_recent_messages("lobby", 50)
    visible = filter_messages_for_user(db_messages, sid)
    for msg in visible:
        lobby.add_message(msg)
    await sio.emit("chat:history", lobby.get_messages_for_player(sid), room=sid)

    await sio.emit(
        "player:entered",
        {
            "id": sid,
            "avatar": avatar,
            "position": player["position"],
            "tile": player.get("tile", {"x": 0, "y": 0}),
        },
        room=room_channel("lobby"),
        skip_sid=sid,
    )


@sio.on("player:move")
async def player_move(sid, data):
    room_id = rooms.get_player_room_id(sid) or "lobby"
    room = rooms.get_room(room_id)
    if not room:
        return
    player = room.set_player_target(sid, {"x": data["x"], "y": data["y"]})
    if player:
        await sio.emit(
            "player:moving",
            {"id": sid, "targetPosition": player["targetPosition"]},
        )


@sio.on("player:action")
async def player_action(sid, data):
    """Player selected an action from the radial menu."""
    action_state = data.get("actionState")  # may be None (stand up)
    target = data.get("target")             # { x, y } anchor position
    teleport = data.get("teleport", False)  # bypass collision (e.g. climb)

    room_id = rooms.get_player_room_id(sid) or "lobby"
    room = rooms.get_room(room_id)
    if not room:
        return

    player = room.get_player(sid)
    if not player:
        return

    if teleport and target:
        # Directly place player at target (e.g. climbing onto table)
        from server.game.movement import clamp_position
        player["position"] = clamp_position(target)
        player["targetPosition"] = None
        player["direction"] = {"x": 0, "y": 0}
        player["actionState"] = action_state
        player["pendingAction"] = None
    elif target:
        # Walk to anchor, then activate action on arrival
        room.set_player_target(sid, target, clear_action=False)
        player["actionState"] = None
        player["pendingAction"] = action_state
    else:
        # Stand up with no movement
        player["actionState"] = action_state
        player["pendingAction"] = None

    await broadcast_room_state(room_id)


@sio.on("player:direction")
async def player_direction(sid, data):
    room_id = rooms.get_player_room_id(sid) or "lobby"
    room = rooms.get_room(room_id)
    if not room:
        return

    player = room.set_player_direction(
        sid,
        {"x": data.get("x", 0), "y": data.get("y", 0)},
    )
    if player:
        await sio.emit(
            "player:direction_update",
            {"id": sid, "direction": player["direction"]},
        )


@sio.on("chat:send")
async def chat_send(sid, data):
    room_id = rooms.get_player_room_id(sid) or "lobby"
    room = rooms.get_room(room_id)
    if not room:
        return

    player = room.get_player(sid)
    if not player:
        return

    text = (data.get("text") or "").strip()
    if not text:
        return

    msg_type = data.get("type", "public")
    recipient_id = data.get("recipientId") if msg_type == "private" else None

    message = create_message(
        sender_id=sid,
        sender_name=player["avatar"]["username"],
        text=text,
        type=msg_type,
        recipient_id=recipient_id,
    )

    room.add_message(message)
    await db.save_message(message, room_id)

    if message["type"] == "public":
        await sio.emit("chat:message", message, room=room_channel(room_id))
    else:
        await sio.emit("chat:message", message, room=sid)
        if recipient_id:
            await sio.emit("chat:message", message, room=recipient_id)

    await broadcast_bubbles(room_id)


@sio.on("combat:attack")
async def combat_attack(sid, data):
    now_ms   = time.time() * 1000
    room_id = rooms.get_player_room_id(sid) or "lobby"
    room = rooms.get_room(room_id)
    if not room:
        return

    attacker = room.get_player(sid)
    if not attacker:
        return

    # Stunned check
    if now_ms < attacker.get("stunnedUntil", 0):
        return

    attack_type = data.get("type")
    target_id   = data.get("targetId")
    if attack_type not in ATTACK_TYPES:
        return

    target = room.get_player(target_id)
    if not target:
        return

    # Server-authoritative range check
    if not is_in_range(attacker["position"], target["position"], attack_type):
        return

    last_atk = attacker.get("lastAttack", {}).get(attack_type, 0)
    if not can_attack(attacker.get("stamina", 0), last_atk, now_ms, attack_type,
                      attacker.get("stunnedUntil", 0)):
        return

    cfg = ATTACK_TYPES[attack_type]
    attacker["stamina"] = max(0.0, attacker.get("stamina", 0) - cfg["stamina_cost"])
    attacker.setdefault("lastAttack", {})[attack_type] = now_ms

    blocked = target.get("blocking", False)
    damage  = calculate_damage(attack_type, blocked)
    new_stamina = apply_hit(target.get("stamina", 100), damage)
    target["stamina"] = new_stamina

    stun_until = 0.0
    if new_stamina <= 0:
        stun_until = now_ms + STUN_DURATION_MS
        target["stunnedUntil"] = stun_until
        if target_id == BOT_ID:
            ai_bot.on_hit(now_ms)

    await sio.emit("combat:hit", {
        "attackerId":     sid,
        "targetId":       target_id,
        "type":           attack_type,
        "damage":         damage,
        "blocked":        blocked,
        "targetStamina":  round(new_stamina),
        "attackerStamina": round(attacker["stamina"]),
        "stunnedUntil":   stun_until,
    }, room=room_channel(room_id))
    await broadcast_room_state(room_id)


@sio.on("combat:block")
async def combat_block(sid, data):
    room_id = rooms.get_player_room_id(sid) or "lobby"
    room = rooms.get_room(room_id)
    if not room:
        return

    player = room.get_player(sid)
    if player:
        player["blocking"] = bool(data.get("blocking", False))
        await sio.emit(
            "combat:block_update",
            {"playerId": sid, "blocking": player["blocking"]},
            room=room_channel(room_id),
        )


@sio.on("room:list")
async def room_list(sid, data=None):
    payload = data or {}
    topic = (payload.get("topic") or "").strip() or None
    access = payload.get("access")
    sort_by = payload.get("sort") or "newest"
    await sio.emit(
        "room:list",
        {
            "rooms": rooms.list_rooms(topic=topic, access=access, sort_by=sort_by),
            "filters": {
                "topic": topic,
                "access": access if access in {"public", "invite"} else "all",
                "sort": sort_by,
            },
        },
        room=sid,
    )


@sio.on("room:create")
async def room_create(sid, data):
    data = data or {}
    room_name = str(data.get("name") or "").strip()[:80]
    if not room_name:
        await sio.emit("error", {"message": "Room name is required"}, room=sid)
        return

    raw_tags = data.get("topicTags")
    topic_tags = [str(tag).strip() for tag in raw_tags][:10] if isinstance(raw_tags, list) else []
    access = "invite" if data.get("access") == "invite" else "public"

    try:
        max_users = int(data.get("maxUsers", 30))
    except (TypeError, ValueError):
        max_users = 30
    max_users = max(1, min(max_users, 200))

    invite_code = str(data.get("inviteCode") or "").strip()[:30] or None
    room = rooms.create_room(
        host_id=sid,
        name=room_name,
        topic_tags=topic_tags,
        access=access,
        max_users=max_users,
        invite_code=invite_code,
    )
    await sio.emit("room:created", room, room=sid)
    await sio.emit("room:list", {"rooms": rooms.list_rooms()}, room=sid)
    await sio.emit("room:list:changed", {}, skip_sid=sid)


@sio.on("room:join")
async def room_join(sid, data):
    data = data or {}
    room_id = data.get("roomId")
    room_id = str(room_id) if room_id else None
    invite_code = str(data.get("inviteCode") or "").strip() or None
    if not room_id:
        await sio.emit("error", {"message": "roomId is required"}, room=sid)
        return

    current_room_id = rooms.get_player_room_id(sid)
    current_room = rooms.get_room(current_room_id) if current_room_id else None
    player = current_room.get_player(sid) if current_room else None
    if not player:
        await sio.emit("error", {"message": "Join the app before joining rooms"}, room=sid)
        return

    avatar = player["avatar"]
    join_error = rooms.get_room_join_error(sid, room_id, invite_code=invite_code)
    if join_error == "not_found":
        await sio.emit("error", {"message": "Room not found"}, room=sid)
        return
    if join_error == "full":
        await sio.emit("error", {"message": "Room is full"}, room=sid)
        return
    if join_error == "forbidden":
        await sio.emit("error", {"message": "Invite code is required for this room"}, room=sid)
        return

    joined = rooms.join_room(sid, avatar, room_id, invite_code=invite_code)
    if not joined:
        await sio.emit("error", {"message": "Unable to join room"}, room=sid)
        return

    if current_room_id and current_room_id != room_id:
        await sio.leave_room(sid, room_channel(current_room_id))
    await sio.enter_room(sid, room_channel(room_id))

    room = rooms.get_room(room_id)
    if room:
        await sio.emit(
            "room:state",
            {"players": [player_payload(p) for p in room.get_all_players()]},
            room=sid,
        )
        db_messages = await db.get_recent_messages(room_id, 50)
        visible = filter_messages_for_user(db_messages, sid)
        await sio.emit("chat:history", visible, room=sid)

    await sio.emit(
        "room:joined",
        {
            "roomId": room_id,
            "currentTile": {"x": joined.get("tile", {}).get("x", 0), "y": joined.get("tile", {}).get("y", 0)},
            "tiles": rooms.get_room_tiles(room_id),
        },
        room=sid,
    )
    await sio.emit("room:list", {"rooms": rooms.list_rooms()}, room=sid)
    if current_room_id and current_room_id != room_id:
        await broadcast_room_state(current_room_id)
    await broadcast_room_state(room_id)
    await sio.emit("room:list:changed", {}, skip_sid=sid)


@sio.on("room:tile:add")
async def room_tile_add(sid, data):
    room_id = rooms.get_player_room_id(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    direction = data.get("direction")
    if direction not in {"left", "right", "top", "bottom"}:
        await sio.emit("error", {"message": "Invalid direction"}, room=sid)
        return

    base_tile = rooms.get_player_tile(sid) or (0, 0)
    created = rooms.add_neighbor_tile(room_id, base_tile, direction)
    if not created:
        await sio.emit("error", {"message": "Cannot add tile in this direction"}, room=sid)
        return

    await sio.emit(
        "room:tiles",
        {"roomId": room_id, "tiles": rooms.get_room_tiles(room_id), "added": created},
        room=room_channel(room_id),
    )


def builder_state_payload(room_id: str) -> dict:
    builder = rooms.get_builder(room_id)
    if not builder:
        return {"tiles": [], "objects": [], "zones": [], "triggers": []}
    return {
        "tiles": builder.list_tiles(),
        "objects": builder.list_objects(),
        "zones": builder.list_zones(),
        "triggers": builder.list_triggers(),
    }


async def broadcast_builder_state(room_id: str) -> None:
    await sio.emit(
        "room:builder:state",
        {"roomId": room_id, **builder_state_payload(room_id)},
        room=room_channel(room_id),
    )


def _current_room_and_builder(sid):
    """Resolve the caller's room id, tile, and builder state, or return
    (None, None, None) after emitting an error."""
    room_id = rooms.get_player_room_id(sid)
    builder = rooms.get_builder(room_id) if room_id else None
    if not room_id or not builder:
        return None, None, None
    tile = rooms.get_player_tile(sid) or (0, 0)
    return room_id, tile, builder


def _is_room_host(sid: str, room_id: str) -> bool:
    return rooms.get_room_host_id(room_id) == sid


@sio.on("room:builder:request")
async def room_builder_request(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    await sio.emit(
        "room:builder:state",
        {"roomId": room_id, **builder_state_payload(room_id)},
        room=sid,
    )
    await sio.emit(
        "room:builder:versions",
        {"roomId": room_id, "versions": builder.list_versions()},
        room=sid,
    )


@sio.on("room:tile:clone")
async def room_tile_clone(sid, data):
    room_id, tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    direction = (data or {}).get("direction")
    if direction not in {"left", "right", "top", "bottom"}:
        await sio.emit("error", {"message": "Invalid direction"}, room=sid)
        return

    cloned = rooms.clone_tile(room_id, tile, direction)
    if not cloned:
        await sio.emit("error", {"message": "Cannot clone tile in this direction"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return cloned


@sio.on("room:tile:delete")
async def room_tile_delete(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    coord = ((data or {}).get("x", 0), (data or {}).get("y", 0))
    if not rooms.delete_tile(room_id, coord):
        await sio.emit("error", {"message": "Cannot delete this tile"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return True


@sio.on("room:tile:configure")
async def room_tile_configure(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    coord = (data.get("x", 0), data.get("y", 0))
    ok = rooms.configure_tile(
        room_id,
        coord,
        label=data.get("label"),
        purpose_tag=data.get("purposeTag"),
        background_style=data.get("backgroundStyle"),
        ambiance_style=data.get("ambianceStyle"),
    )
    if not ok:
        await sio.emit("error", {"message": "Unknown tile"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return builder.get_tile(coord)


@sio.on("room:object:create")
async def room_object_create(sid, data):
    room_id, tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        obj = builder.create_object(
            object_id=data.get("objectId") or f"obj-{uuid.uuid4().hex[:8]}",
            object_type=data["objectType"],
            tile=tile,
            x=data["x"],
            y=data["y"],
            width=data.get("width"),
            height=data.get("height"),
            size_preset=data.get("sizePreset"),
            rotation=data.get("rotation", 0.0),
            interaction_radius=data.get("interactionRadius", 20.0),
            color=data.get("color"),
            material=data.get("material"),
            edit_permission=data.get("editPermission", "owner_only"),
            interaction_cooldown_ms=data.get("interactionCooldownMs", 0.0),
            created_by=sid,
            config=data.get("config"),
        )
    except (ValidationError, ValueError, KeyError) as exc:
        await sio.emit("error", {"message": f"Invalid object: {exc}"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return obj


@sio.on("room:object:move")
async def room_object_move(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        obj = builder.move_object(
            data["objectId"], data["x"], data["y"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return obj


@sio.on("room:object:resize")
async def room_object_resize(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        obj = builder.resize_object(
            data["objectId"], data["width"], data["height"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return obj


@sio.on("room:object:rotate")
async def room_object_rotate(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        obj = builder.rotate_object(
            data["objectId"], data["rotation"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return obj


@sio.on("room:object:style")
async def room_object_style(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        if "sizePreset" in data:
            obj = builder.set_object_size_preset(
                data["objectId"], data["sizePreset"],
                requester_id=sid, is_room_host=_is_room_host(sid, room_id),
            )
        obj = builder.set_object_style(
            data["objectId"], color=data.get("color"), material=data.get("material"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return obj


@sio.on("room:object:permission")
async def room_object_permission(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        obj = builder.set_object_edit_permission(
            data["objectId"], data["editPermission"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return obj


@sio.on("room:object:interact")
async def room_object_interact(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        result = builder.interact_with_object(
            data["objectId"], data["interactionType"],
            requester_id=sid, now_ms=time.time() * 1000,
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await sio.emit("room:object:interacted", {"roomId": room_id, **result}, room=sid)
    return result


@sio.on("room:book:add")
async def room_book_add(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        book = builder.add_book(
            data["objectId"], data["bookId"], title=data["title"], content_body=data["contentBody"],
            author=data.get("author"), summary=data.get("summary"), reading_level=data.get("readingLevel"),
            content_type=data.get("contentType", "inline"), est_read_minutes=data.get("estReadMinutes"),
            cover_url=data.get("coverUrl"), requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError, ValidationError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return book


@sio.on("room:book:remove")
async def room_book_remove(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        removed = builder.remove_book(
            data["objectId"], data["bookId"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return
    if not removed:
        await sio.emit("error", {"message": "Unknown book"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return True


@sio.on("room:book:progress:save")
async def room_book_progress_save(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        progress = builder.save_reading_progress(
            data["objectId"], data["bookId"], sid, data["progress"], now_ms=time.time() * 1000,
        )
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return progress


async def _broadcast_sync_session(room_id: str, object_id: str, now_ms: float) -> None:
    builder = rooms.get_builder(room_id)
    session = builder.get_watch_sync(object_id, now_ms=now_ms) if builder else None
    await sio.emit(
        "room:media:sync:updated",
        {"roomId": room_id, "objectId": object_id, "session": session},
        room=room_channel(room_id),
    )


@sio.on("room:media:video:add")
async def room_media_video_add(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        video = builder.add_video(
            data["objectId"], data["videoId"], title=data["title"], youtube_video_id=data["youtubeVideoId"],
            description=data.get("description"), requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError, ValidationError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return video


@sio.on("room:media:video:remove")
async def room_media_video_remove(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        removed = builder.remove_video(
            data["objectId"], data["videoId"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return
    if not removed:
        await sio.emit("error", {"message": "Unknown video"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return True


@sio.on("room:media:track:add")
async def room_media_track_add(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        track = builder.add_track(
            data["objectId"], data["trackId"], title=data["title"], youtube_video_id=data["youtubeVideoId"],
            artist=data.get("artist"), duration_seconds=data.get("durationSeconds"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError, ValidationError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return track


@sio.on("room:media:track:remove")
async def room_media_track_remove(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        removed = builder.remove_track(
            data["objectId"], data["trackId"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return
    if not removed:
        await sio.emit("error", {"message": "Unknown track"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return True


@sio.on("room:media:sync:start")
async def room_media_sync_start(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    now_ms = time.time() * 1000
    try:
        session = builder.start_watch_sync(data["objectId"], host_id=sid, item_id=data["itemId"], now_ms=now_ms)
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await _broadcast_sync_session(room_id, data["objectId"], now_ms)
    return session


@sio.on("room:media:sync:join")
async def room_media_sync_join(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        session = builder.join_watch_sync(data["objectId"], user_id=sid)
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await _broadcast_sync_session(room_id, data["objectId"], time.time() * 1000)
    return session


@sio.on("room:media:sync:leave")
async def room_media_sync_leave(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        builder.leave_watch_sync(data["objectId"], user_id=sid)
    except ValueError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await _broadcast_sync_session(room_id, data["objectId"], time.time() * 1000)
    return True


@sio.on("room:media:sync:update")
async def room_media_sync_update(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    now_ms = time.time() * 1000
    try:
        session = builder.update_watch_sync(
            data["objectId"], requester_id=sid, is_playing=data["isPlaying"],
            position_seconds=data["positionSeconds"], now_ms=now_ms,
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await _broadcast_sync_session(room_id, data["objectId"], now_ms)
    return session


@sio.on("room:media:sync:end")
async def room_media_sync_end(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        ended = builder.end_watch_sync(data["objectId"], requester_id=sid)
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return
    if not ended:
        await sio.emit("error", {"message": "No active sync session"}, room=sid)
        return

    await _broadcast_sync_session(room_id, data["objectId"], time.time() * 1000)
    return True


def _call_openai_compatible_endpoint(
    api_base_url: str, api_key: str, knowledge_base: str | None, user_message: str,
) -> str:
    """Server-side call to a room-admin-configured OpenAI-compatible chat
    completion endpoint. The API key is only ever used here, server-side,
    and is never sent to or exposed by any client-facing payload."""
    messages = []
    if knowledge_base:
        messages.append({"role": "system", "content": knowledge_base})
    messages.append({"role": "user", "content": user_message})

    response = httpx.post(
        f"{api_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "gpt-3.5-turbo", "messages": messages},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


@sio.on("room:character:configure")
async def room_character_configure(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        character = builder.configure_character(
            data["objectId"], name=data["name"], role=data["role"], start_node_id=data["startNodeId"],
            portrait_url=data.get("portraitUrl"), requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return character


@sio.on("room:character:knowledge_base:set")
async def room_character_knowledge_base_set(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        character = builder.set_character_knowledge_base(
            data["objectId"], data["content"], requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return character


@sio.on("room:character:generative:configure")
async def room_character_generative_configure(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        character = builder.configure_character_generative_mode(
            data["objectId"], api_base_url=data.get("apiBaseUrl"), api_key=data.get("apiKey"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return character


@sio.on("room:character:node:add")
async def room_character_node_add(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        node = builder.add_story_node(
            data["objectId"], data["nodeId"], character_line=data["characterLine"],
            choices=data.get("choices"), completion_flag=data.get("completionFlag", False),
            knowledge_check=data.get("knowledgeCheck"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError, ValidationError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return node


@sio.on("room:character:node:list")
async def room_character_node_list(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        nodes = builder.list_story_nodes(data["objectId"])
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return nodes


@sio.on("room:character:talk")
async def room_character_talk(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        result = builder.talk_to_character(
            data["objectId"], requester_id=sid, choice_index=data.get("choiceIndex"),
        )
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return result


@sio.on("room:character:ask")
async def room_character_ask(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}

    def caller(api_base_url, api_key, knowledge_base, user_message):
        return _call_openai_compatible_endpoint(api_base_url, api_key, knowledge_base, user_message)

    try:
        result = await asyncio.to_thread(
            builder.ask_character, data["objectId"], sid, data["userMessage"], caller,
        )
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return result



async def room_object_duplicate(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    new_object_id = data.get("newObjectId") or f"obj-{uuid.uuid4().hex[:8]}"
    try:
        obj = builder.duplicate_object(data["objectId"], new_object_id, requester_id=sid)
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return obj


@sio.on("room:object:lock")
async def room_object_lock(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        obj = builder.set_locked(
            data["objectId"], bool(data.get("locked", True)),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return obj


@sio.on("room:object:layer")
async def room_object_layer(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    action = data.get("action")
    is_host = _is_room_host(sid, room_id)
    try:
        if action == "front":
            obj = builder.bring_to_front(data["objectId"], requester_id=sid, is_room_host=is_host)
        elif action == "back":
            obj = builder.send_to_back(data["objectId"], requester_id=sid, is_room_host=is_host)
        else:
            await sio.emit("error", {"message": "Invalid layer action"}, room=sid)
            return
    except (KeyError, PermissionError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return obj


@sio.on("room:object:delete")
async def room_object_delete(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        deleted = builder.delete_object(
            data["objectId"], requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return
    if not deleted:
        await sio.emit("error", {"message": "Unknown object"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return True


@sio.on("room:zone:create")
async def room_zone_create(sid, data):
    room_id, tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        zone = builder.create_zone(
            zone_id=data.get("zoneId") or f"zone-{uuid.uuid4().hex[:8]}",
            tile=tile,
            zone_type=data["zoneType"],
            min_x=data["minX"],
            min_y=data["minY"],
            max_x=data["maxX"],
            max_y=data["maxY"],
        )
    except (ValidationError, ValueError, KeyError) as exc:
        await sio.emit("error", {"message": f"Invalid zone: {exc}"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return zone


@sio.on("room:zone:delete")
async def room_zone_delete(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    if not builder.delete_zone((data or {}).get("zoneId")):
        await sio.emit("error", {"message": "Unknown zone"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return True


@sio.on("room:trigger:create")
async def room_trigger_create(sid, data):
    room_id, tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        trigger = builder.create_trigger(
            trigger_id=data.get("triggerId") or f"trigger-{uuid.uuid4().hex[:8]}",
            tile=tile,
            zone_id=data.get("zoneId"),
            event_type=data["eventType"],
            payload=data.get("payload", {}),
            repeatable=data.get("repeatable", False),
            cooldown_ms=data.get("cooldownMs", 0.0),
        )
    except (ValueError, KeyError) as exc:
        await sio.emit("error", {"message": f"Invalid trigger: {exc}"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return trigger


@sio.on("room:trigger:delete")
async def room_trigger_delete(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    if not builder.delete_trigger((data or {}).get("triggerId")):
        await sio.emit("error", {"message": "Unknown trigger"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return True


@sio.on("room:version:save")
async def room_version_save(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    version = builder.save_draft(
        snapshot=data.get("snapshot", builder_state_payload(room_id)),
        created_by=sid,
        change_notes=data.get("changeNotes"),
    )
    await sio.emit(
        "room:builder:versions",
        {"roomId": room_id, "versions": builder.list_versions()},
        room=room_channel(room_id),
    )
    return version


@sio.on("room:version:publish")
async def room_version_publish(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    try:
        version = builder.publish((data or {}).get("versionNumber"), published_by=sid)
    except ValueError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await sio.emit(
        "room:builder:versions",
        {"roomId": room_id, "versions": builder.list_versions()},
        room=room_channel(room_id),
    )
    return version


@sio.on("room:version:rollback")
async def room_version_rollback(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    try:
        snapshot = builder.rollback((data or {}).get("versionNumber"))
    except ValueError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await sio.emit(
        "room:builder:rollback",
        {"roomId": room_id, "snapshot": snapshot},
        room=sid,
    )
    return snapshot


socket_app = socketio.ASGIApp(sio, app)


def main():
    uvicorn.run("server.main:socket_app", host="0.0.0.0", port=PORT, reload=False)


if __name__ == "__main__":
    main()
