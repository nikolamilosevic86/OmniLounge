import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

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
from server.game.moderation import contains_external_link
from server.game.movement import move_by_direction, move_toward
from server.game.metrics import MetricsCollector
from server.game.room import Room
from server.game.rooms_registry import RoomsRegistry
from server.game.tile_navigation import tiles_within_radius

DIST_DIR = Path(__file__).resolve().parent.parent / "dist"

logger  = logging.getLogger(__name__)
sio     = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
db      = Database()
rooms   = RoomsRegistry()
ai_bot  = AIBot()
metrics = MetricsCollector()
_game_loop_task: asyncio.Task | None = None

# Wrap sio.on() registration so every "@sio.on(...)" handler below is timed and
# its success/failure recorded in `metrics`, without needing to touch each
# handler individually. Handlers registered via "@sio.event" (connect/
# disconnect) are intentionally left uninstrumented for now.
_uninstrumented_sio_on = sio.on


def _instrumented_sio_on(event, handler=None, namespace=None):
    def register(func):
        async def timed_handler(*args, **kwargs):
            start = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                metrics.record(event, (time.monotonic() - start) * 1000.0, success=True)
                return result
            except Exception:
                metrics.record(event, (time.monotonic() - start) * 1000.0, success=False)
                raise
        return _uninstrumented_sio_on(event, namespace=namespace)(timed_handler)

    if handler is not None:
        return register(handler)
    return register


sio.on = _instrumented_sio_on



def player_payload(player: dict, moderation=None) -> dict:
    now_ms = time.time() * 1000
    payload = {
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
    if moderation:
        payload["role"] = moderation.get_role(player["id"])
        payload["muted"] = moderation.is_muted(player["id"])
    return payload


def room_channel(room_id: str) -> str:
    return f"room:{room_id}"


def _valid_position(pos: Any) -> bool:
    """True if `pos` is a dict with numeric x/y — the minimum shape that
    movement.clamp_position() can safely process. A raw/malicious socket
    client can send any JSON, so handlers must validate before forwarding
    to clamp_position() rather than trusting client-supplied coordinates."""
    if not isinstance(pos, dict):
        return False
    x, y = pos.get("x"), pos.get("y")
    return isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool) and not isinstance(y, bool)


def _valid_tile_coord(x: Any, y: Any) -> bool:
    """True if `x`/`y` are ints — tile coordinates are used as dict keys
    (`(x, y)` tuples) by RoomBuilderState, so a non-hashable client value
    (e.g. a JSON list/object) would raise an uncaught `TypeError: unhashable
    type` on the resulting dict lookup rather than a clean 'unknown tile'
    error. Tiles are always integer-indexed (see RoomObjectPlacementModel's
    tile_x/tile_y), so floats are rejected too."""
    return isinstance(x, int) and isinstance(y, int) and not isinstance(x, bool) and not isinstance(y, bool)


def all_players_payload(room_id: str) -> list[dict]:
    room = rooms.get_room(room_id)
    if not room:
        return []
    moderation = rooms.get_moderation(room_id)
    return [player_payload(p, moderation) for p in room.get_all_players()]


async def broadcast_room_state(room_id: str) -> None:
    await sio.emit("room:state", {"players": all_players_payload(room_id)}, room=room_channel(room_id))


async def broadcast_bubbles(room_id: str) -> None:
    room = rooms.get_room(room_id)
    if not room:
        return
    for player in room.get_all_players():
        bubbles = room.get_active_bubbles(player["id"])
        await sio.emit("chat:bubbles", bubbles, room=player["id"])


def _tile_collision_obstacles(room_id: str, tile: Any, requester_id: str | None = None) -> list[dict[str, float]]:
    """Builder-placed objects on a player's current tile must block movement
    just like the lobby's hardcoded furniture -- otherwise a room-builder
    user can place a table/sofa/etc. that players simply walk straight
    through. Returns a list of `{x, y, w, h}` AABBs for `move_by_direction`/
    `move_toward` to treat as extra obstacles.

    `requester_id` (design doc feature_designs/escape_room_feature_design.md
    §5.1) skips only `escape_door` objects that specific player has
    personally opened, so the door keeps blocking every other visitor who
    hasn't opened it themselves -- every other object type is unaffected."""
    builder = rooms.get_builder(room_id)
    if builder is None:
        return []
    if isinstance(tile, dict):
        tile_coord = (tile.get("x", 0), tile.get("y", 0))
    else:
        tile_coord = (0, 0)
    if not (isinstance(tile_coord[0], int) and isinstance(tile_coord[1], int)):
        return []
    obstacles = []
    for obj in builder.list_objects(tile=tile_coord):
        if (
            obj["objectType"] == "escape_door"
            and requester_id is not None
            and builder.has_opened_door(obj["objectId"], requester_id)
        ):
            continue
        obstacles.append({"x": obj["x"], "y": obj["y"], "w": obj["width"], "h": obj["height"]})
    return obstacles


def _evaluate_area_triggers(
    room_id: str,
    player_id: str,
    tile: Any,
    position: dict[str, float],
    now_ms: float,
    fired_triggers: list[dict] | None,
) -> None:
    """Drive `RoomBuilderState.evaluate_area_enter` for one player's new
    position (design doc feature_designs/escape_room_feature_design.md §6.3).
    A no-op unless the caller opts in with an output list, so every
    pre-existing caller of `apply_player_movement` is unaffected."""
    if fired_triggers is None:
        return
    builder = rooms.get_builder(room_id)
    if builder is None:
        return
    tile_coord = (tile.get("x", 0), tile.get("y", 0)) if isinstance(tile, dict) else tile
    for fired in builder.evaluate_area_enter(player_id, tile_coord, position["x"], position["y"], now_ms):
        fired_triggers.append({"playerId": player_id, **fired})


def apply_player_movement(
    room: Room, room_id: str, player: dict, now_ms: float, fired_triggers: list[dict] | None = None,
) -> bool:
    """Apply direction or click-target movement (and tile transitions) for a
    single player. Returns True if the player's position/tile changed this tick.

    This must run for every player in the room, including the AI bot: only
    stamina regeneration is bot-exempt, not movement processing.

    `fired_triggers` (design doc §6.3) is an optional output list: when
    given, any scripted trigger whose zone the player just entered is
    appended to it, so the game loop can react (e.g. `reveal_object`)
    without every other caller of this function having to change.
    """
    extra_obstacles = _tile_collision_obstacles(room_id, player.get("tile"), requester_id=player.get("id"))

    direction = player.get("direction", {"x": 0, "y": 0})
    if direction["x"] != 0 or direction["y"] != 0:
        new_pos = move_by_direction(player["position"], direction, MOVE_SPEED, extra_obstacles=extra_obstacles)
        transition = rooms.transition_player_tile_if_needed(player["id"], room_id, new_pos)
        if transition:
            player["tile"] = transition["tile"]
            room.update_player_position(player["id"], transition["position"])
            _evaluate_area_triggers(
                room_id, player["id"], transition["tile"], transition["position"], now_ms, fired_triggers,
            )
        else:
            room.update_player_position(player["id"], new_pos)
            _evaluate_area_triggers(room_id, player["id"], player.get("tile"), new_pos, now_ms, fired_triggers)
        return True

    target = player.get("targetPosition")
    if target:
        new_pos = move_toward(player["position"], target, MOVE_SPEED, extra_obstacles=extra_obstacles)
        transition = rooms.transition_player_tile_if_needed(player["id"], room_id, new_pos)
        if transition:
            player["tile"] = transition["tile"]
            room.update_player_position(player["id"], transition["position"])
            _evaluate_area_triggers(
                room_id, player["id"], transition["tile"], transition["position"], now_ms, fired_triggers,
            )
            player["targetPosition"] = None
            if player.get("pendingAction") is not None:
                player["actionState"] = player["pendingAction"]
                player["pendingAction"] = None
            return True

        room.update_player_position(player["id"], new_pos)
        _evaluate_area_triggers(room_id, player["id"], player.get("tile"), new_pos, now_ms, fired_triggers)
        if new_pos["x"] == target["x"] and new_pos["y"] == target["y"]:
            player["targetPosition"] = None
            if player.get("pendingAction") is not None:
                player["actionState"] = player["pendingAction"]
                player["pendingAction"] = None
        return True

    return False


async def tick_guided_tours(room_id: str, now_ms: float) -> None:
    """Walk any AI characters that are currently giving a guided tour, and
    push their new positions to the room.

    Positions are sent on a dedicated lightweight `room:npc:moved` event
    rather than by re-broadcasting the whole builder state each tick: the
    builder-state payload contains every object, zone and trigger in the
    room, which would be wasteful at the game-loop tick rate (and is only
    consumed by clients in build mode anyway).
    """
    builder = rooms.get_builder(room_id)
    if builder is None:
        return
    try:
        results = builder.tick_character_tours(now_ms)
    except Exception:  # a broken tour must never take the whole game loop down
        logger.exception("guided tour tick failed for room %s", room_id)
        return

    for result in results:
        tile = result["tile"]
        await sio.emit("room:npc:moved", {
            "roomId": room_id,
            "objectId": result["objectId"],
            "tile": {"x": tile[0], "y": tile[1]},
            "position": result["position"],
            "status": result["status"],
            "waypointIndex": result["waypointIndex"],
            "finished": result["finished"],
        }, room=room_channel(room_id))

        # Speak the waypoint's label on arrival so a tour reads as the
        # character narrating the room, not just silently walking off.
        arrived = result["arrived"]
        if arrived and arrived.get("label"):
            await sio.emit("room:npc:say", {
                "roomId": room_id,
                "objectId": result["objectId"],
                "text": arrived["label"][:200],
            }, room=room_channel(room_id))


async def handle_fired_trigger(room_id: str, fired: dict) -> None:
    """React to one scripted trigger firing for one visitor (design doc
    feature_designs/escape_room_feature_design.md §6.3). Every fired
    trigger is echoed to that visitor as a generic event first (useful for
    build-mode/tour-style triggers with client-side behavior); `reveal_object`
    is the one eventType with server-side behavior today -- it marks a
    hidden_item revealed for that visitor and pushes them a personalized
    builder-state refresh, the same targeted-broadcast pattern already used
    for `room:npc:moved`, rather than a full-room rebroadcast that would
    leak the reveal to every other visitor."""
    player_id = fired["playerId"]
    await sio.emit(
        "room:trigger:fired",
        {
            "roomId": room_id,
            "triggerId": fired["triggerId"],
            "eventType": fired["eventType"],
            "payload": fired["payload"],
        },
        room=player_id,
    )
    if fired["eventType"] != "reveal_object":
        return
    object_id = fired["payload"].get("objectId")
    if not object_id:
        return
    builder = rooms.get_builder(room_id)
    if builder is None:
        return
    builder.reveal_item(player_id, object_id)
    await sio.emit(
        "room:builder:state",
        {
            "roomId": room_id,
            **builder_state_payload(
                room_id, requester_id=player_id, is_room_host=_is_room_host(player_id, room_id),
            ),
        },
        room=player_id,
    )


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
            fired_triggers: list[dict] = []
            for player in room.get_all_players():
                # Regen stamina for everyone except AI bot (managed by its own tick)
                if player["id"] != BOT_ID:
                    player["stamina"] = regen_stamina(player.get("stamina", 100), delta_ms)

                # Skip movement while stunned
                if now_ms < player.get("stunnedUntil", 0):
                    continue

                if apply_player_movement(room, room_id, player, now_ms, fired_triggers=fired_triggers):
                    moved = True

            moved_by_room[room_id] = moved
            for fired in fired_triggers:
                await handle_fired_trigger(room_id, fired)
            await tick_guided_tours(room_id, now_ms)
            await tick_escape_sessions(room_id, now_ms)

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


@app.get("/metrics")
async def get_metrics():
    return {
        "events": metrics.snapshot(),
        "rooms_active": len(rooms.rooms),
        "players_connected": len(rooms.player_room),
    }


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
    await sio.emit(
        "room:builder:state",
        {"roomId": "lobby", **builder_state_payload("lobby", requester_id=sid, is_room_host=_is_room_host(sid, "lobby"))},
        room=sid,
    )

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
    data = data or {}
    if not _valid_position(data):
        return
    player = room.set_player_target(sid, {"x": data["x"], "y": data["y"]})
    if player:
        await sio.emit(
            "player:moving",
            {"id": sid, "targetPosition": player["targetPosition"]},
            room=room_channel(room_id),
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

    if teleport and target and _valid_position(target):
        # Directly place player at target (e.g. climbing onto table)
        from server.game.movement import clamp_position
        player["position"] = clamp_position(target)
        player["targetPosition"] = None
        player["direction"] = {"x": 0, "y": 0}
        player["actionState"] = action_state
        player["pendingAction"] = None
    elif target and _valid_position(target):
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

    data = data or {}
    if not _valid_position(data):
        return

    player = room.set_player_direction(
        sid,
        {"x": data["x"], "y": data["y"]},
    )
    if player:
        await sio.emit(
            "player:direction_update",
            {"id": sid, "direction": player["direction"]},
            room=room_channel(room_id),
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

    text = (data.get("text") or "").strip()[:200]
    if not text:
        return

    moderation = rooms.get_moderation(room_id)
    if moderation and moderation.is_muted(sid):
        await sio.emit("error", {"message": "You are muted in this room"}, room=sid)
        return

    if moderation and not moderation.are_external_links_allowed() and contains_external_link(text):
        await sio.emit("error", {"message": "External links are not allowed in this room"}, room=sid)
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
    if not isinstance(target_id, str):
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
    room_style = data.get("roomStyle")
    room = rooms.create_room(
        host_id=sid,
        name=room_name,
        topic_tags=topic_tags,
        access=access,
        max_users=max_users,
        invite_code=invite_code,
        room_style=room_style,
    )
    await sio.emit(
        "room:created",
        {**room, "hostToken": rooms.get_room_host_token(room["id"])},
        room=sid,
    )
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
    if join_error == "banned":
        await sio.emit("error", {"message": "You are banned from this room"}, room=sid)
        return

    joined = rooms.join_room(sid, avatar, room_id, invite_code=invite_code)
    if not joined:
        await sio.emit("error", {"message": "Unable to join room"}, room=sid)
        return

    host_token = data.get("hostToken")
    if host_token:
        # Lets a room creator who reconnected with a new session id (page
        # refresh, dropped connection) reclaim ownership of a room they
        # created, since identity is otherwise tied to the ephemeral sid.
        rooms.reclaim_host(room_id, sid, str(host_token))

    if current_room_id and current_room_id != room_id:
        await sio.leave_room(sid, room_channel(current_room_id))
    await sio.enter_room(sid, room_channel(room_id))

    room = rooms.get_room(room_id)
    if room:
        await sio.emit(
            "room:state",
            {"players": all_players_payload(room_id)},
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
            "hostId": rooms.get_room_host_id(room_id),
            "myRole": (rooms.get_moderation(room_id).get_role(sid) if rooms.get_moderation(room_id) else "participant"),
            "roomStyle": rooms.get_room_style(room_id),
        },
        room=sid,
    )
    await sio.emit(
        "room:builder:state",
        {"roomId": room_id, **builder_state_payload(room_id)},
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


def builder_state_payload(
    room_id: str, tiles: set[tuple[int, int]] | None = None,
    requester_id: str | None = None, is_room_host: bool = False,
) -> dict:
    builder = rooms.get_builder(room_id)
    if not builder:
        return {"tiles": [], "objects": [], "zones": [], "triggers": []}
    objects = (
        builder.list_objects_for_tiles(tiles, requester_id=requester_id, is_room_host=is_room_host)
        if tiles is not None
        else builder.list_objects(requester_id=requester_id, is_room_host=is_room_host)
    )
    return {
        "tiles": builder.list_tiles(),
        "objects": objects,
        "zones": builder.list_zones(),
        "triggers": builder.list_triggers(),
    }


async def broadcast_builder_state(room_id: str) -> None:
    """Unlike most other room-wide broadcasts, this cannot be a single
    `room=room_channel(room_id)` emit: unrevealed `hidden_item` objects must
    never reach a visitor's client at all (design doc
    feature_designs/escape_room_feature_design.md §5.2/§12), and that
    filtering is per-visitor (`RoomBuilderState.list_objects`'s
    `requester_id`). So every connected player in the room gets their own
    personalized payload, targeted at their own sid, mirroring the
    per-caller pattern already used by `room_builder_request`."""
    room = rooms.get_room(room_id)
    if room is None:
        await sio.emit(
            "room:builder:state",
            {"roomId": room_id, **builder_state_payload(room_id)},
            room=room_channel(room_id),
        )
        return
    for player in room.get_all_players():
        player_id = player["id"]
        await sio.emit(
            "room:builder:state",
            {
                "roomId": room_id,
                **builder_state_payload(
                    room_id, requester_id=player_id, is_room_host=_is_room_host(player_id, room_id),
                ),
            },
            room=player_id,
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


def _display_name(sid: str, room_id: str) -> str:
    room = rooms.get_room(room_id)
    player = room.get_player(sid) if room else None
    if player is None:
        return sid
    return player["avatar"]["username"]


@sio.on("room:builder:request")
async def room_builder_request(sid, data):
    room_id, tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    radius = (data or {}).get("radius")
    tiles = tiles_within_radius(tile, radius) if isinstance(radius, int) and radius >= 0 else None

    await sio.emit(
        "room:builder:state",
        {
            "roomId": room_id,
            **builder_state_payload(
                room_id, tiles, requester_id=sid, is_room_host=_is_room_host(sid, room_id),
            ),
        },
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

    data = data or {}
    x, y = data.get("x", 0), data.get("y", 0)
    if not _valid_tile_coord(x, y):
        await sio.emit("error", {"message": "Invalid tile coordinates"}, room=sid)
        return

    coord = (x, y)
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
    x, y = data.get("x", 0), data.get("y", 0)
    if not _valid_tile_coord(x, y):
        await sio.emit("error", {"message": "Invalid tile coordinates"}, room=sid)
        return

    coord = (x, y)
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
    except (KeyError, PermissionError, ValueError) as exc:
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
    except (KeyError, PermissionError, ValueError) as exc:
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
    now_ms = time.time() * 1000
    try:
        result = builder.interact_with_object(
            data["objectId"], data["interactionType"],
            requester_id=sid, now_ms=now_ms, display_name=_display_name(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await sio.emit("room:object:interacted", {"roomId": room_id, **result}, room=sid)

    # A door with no `destinationTile` opening for the first time is a win
    # trigger (design doc §5.1/§8.3); `mark_won` inside `attempt_open_door`
    # is a no-op unless that visitor's session was `in_progress`, so check
    # status afterwards rather than assuming every fresh open is a win.
    payload = result.get("payload", {})
    if (
        result.get("objectType") == "escape_door"
        and result.get("interactionType") == "attempt_open"
        and payload.get("opened")
        and not payload.get("alreadyOpen")
        and payload.get("destinationTile") is None
    ):
        if builder.get_escape_status(sid, now_ms=now_ms)["state"] == "won":
            won_payload = {"roomId": room_id, "displayName": _display_name(sid, room_id)}
            await sio.emit("room:escape:won", won_payload, room=sid)
            await sio.emit("room:escape:won", won_payload, room=room_channel(room_id), skip_sid=sid)

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
    and is never sent to or exposed by any client-facing payload.
    `api_base_url` is validated against `is_safe_external_url` at
    configure-time (see `StoryEngine.configure_generative_mode`); redirects
    are not followed here as an additional SSRF safeguard."""
    messages = []
    if knowledge_base:
        messages.append({"role": "system", "content": knowledge_base})
    messages.append({"role": "user", "content": user_message})

    response = httpx.post(
        f"{api_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "gpt-3.5-turbo", "messages": messages},
        timeout=10.0,
        follow_redirects=False,
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


@sio.on("room:character:appearance")
async def room_character_appearance(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    appearance = data.get("appearance")
    if not isinstance(appearance, dict):
        await sio.emit("error", {"message": "Invalid appearance payload"}, room=sid)
        return
    try:
        character = builder.configure_character_appearance(
            data["objectId"], appearance, requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return character


@sio.on("room:character:knowledge_base:title:set")
async def room_character_knowledge_base_title_set(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        character = builder.set_character_knowledge_base_title(
            data["objectId"], data.get("title"), requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return character


@sio.on("room:character:knowledge_base:document:add")
async def room_character_knowledge_base_document_add(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    doc_id = data.get("docId") or f"doc-{uuid.uuid4().hex[:8]}"
    try:
        character = builder.add_character_knowledge_document(
            data["objectId"], doc_id, data["title"], data["docType"],
            content=data.get("content"), url=data.get("url"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError, ValidationError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return character


@sio.on("room:character:knowledge_base:document:remove")
async def room_character_knowledge_base_document_remove(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        character = builder.remove_character_knowledge_document(
            data["objectId"], data["docId"], requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return character


@sio.on("room:character:knowledge_base:document:update")
async def room_character_knowledge_base_document_update(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        character = builder.update_character_knowledge_document(
            data["objectId"], data["docId"], data["title"], data["docType"],
            content=data.get("content"), url=data.get("url"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError, ValidationError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return character


@sio.on("room:character:knowledge_base:document:reorder")
async def room_character_knowledge_base_document_reorder(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        character = builder.move_character_knowledge_document(
            data["objectId"], data["docId"], data["direction"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError, ValidationError) as exc:
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
            builder.ask_character, data["objectId"], sid, data["userMessage"], caller, time.time() * 1000,
        )
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return result


@sio.on("room:character:waypoint:add")
async def room_character_waypoint_add(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    waypoint_id = data.get("waypointId") or f"wp-{uuid.uuid4().hex[:8]}"
    try:
        waypoints = builder.add_character_waypoint(
            data["objectId"], waypoint_id, data["x"], data["y"], label=data.get("label"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return waypoints


@sio.on("room:character:waypoint:remove")
async def room_character_waypoint_remove(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        waypoints = builder.remove_character_waypoint(
            data["objectId"], data["waypointId"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return waypoints


@sio.on("room:character:waypoint:reorder")
async def room_character_waypoint_reorder(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        waypoints = builder.move_character_waypoint(
            data["objectId"], data["waypointId"], data["direction"],
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return waypoints


@sio.on("room:character:waypoint:clear")
async def room_character_waypoint_clear(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        waypoints = builder.clear_character_waypoints(
            data["objectId"], requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return waypoints


@sio.on("room:character:tour:start")
async def room_character_tour_start(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        tour = builder.start_character_tour(data["objectId"], requester_id=sid, now_ms=time.time() * 1000)
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return tour


@sio.on("room:character:tour:stop")
async def room_character_tour_stop(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        tour = builder.stop_character_tour(data["objectId"], requester_id=sid)
    except (KeyError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return tour


@sio.on("room:object:duplicate")
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


@sio.on("room:role:assign")
async def room_role_assign(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    target_id = data.get("targetId")
    role = data.get("role")
    try:
        moderation.assign_role(target_id, role, actor_id=sid)
    except (PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    result = {"targetId": target_id, "role": moderation.get_role(target_id)}
    await sio.emit("room:role:updated", result, room=room_channel(room_id))
    return result


@sio.on("room:moderation:mute")
async def room_moderation_mute(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    target_id = (data or {}).get("targetId")
    try:
        moderation.mute(target_id, actor_id=sid)
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    result = {"targetId": target_id, "muted": True}
    await sio.emit("room:moderation:muted", result, room=room_channel(room_id))
    return result


@sio.on("room:moderation:unmute")
async def room_moderation_unmute(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    target_id = (data or {}).get("targetId")
    try:
        moderation.unmute(target_id, actor_id=sid)
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    result = {"targetId": target_id, "muted": False}
    await sio.emit("room:moderation:muted", result, room=room_channel(room_id))
    return result


async def _remove_player_from_room(target_id: str, room_id: str, reason: str) -> None:
    """Force a player out of `room_id` back to the lobby, notifying them."""
    target_room = rooms.get_room(room_id)
    target_player = target_room.get_player(target_id) if target_room else None
    if not target_player:
        return
    avatar = target_player["avatar"]

    new_room_id = "lobby"
    if room_id != "lobby":
        rooms.join_room(target_id, avatar, new_room_id)
        await sio.leave_room(target_id, room_channel(room_id))
        await sio.enter_room(target_id, room_channel(new_room_id))
    else:
        rooms.leave_current_room(target_id)

    new_room_moderation = rooms.get_moderation(new_room_id)
    await sio.emit(
        "room:moderation:removed",
        {
            "reason": reason,
            "roomId": room_id,
            "newRoomId": new_room_id,
            "currentTile": {"x": 0, "y": 0},
            "tiles": rooms.get_room_tiles(new_room_id),
            "hostId": rooms.get_room_host_id(new_room_id),
            "myRole": (new_room_moderation.get_role(target_id) if new_room_moderation else "participant"),
            "roomStyle": rooms.get_room_style(new_room_id),
        },
        room=target_id,
    )
    if new_room_id != room_id:
        db_messages = await db.get_recent_messages(new_room_id, 50)
        visible = filter_messages_for_user(db_messages, target_id)
        await sio.emit("chat:history", visible, room=target_id)
        await sio.emit(
            "room:builder:state",
            {
                "roomId": new_room_id,
                **builder_state_payload(
                    new_room_id, requester_id=target_id, is_room_host=_is_room_host(target_id, new_room_id),
                ),
            },
            room=target_id,
        )
        await broadcast_room_state(new_room_id)
    await broadcast_room_state(room_id)


@sio.on("room:moderation:kick")
async def room_moderation_kick(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    target_id = (data or {}).get("targetId")
    try:
        moderation.kick(target_id, actor_id=sid)
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await _remove_player_from_room(target_id, room_id, "kicked")
    return {"targetId": target_id, "kicked": True}


@sio.on("room:moderation:ban")
async def room_moderation_ban(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    target_id = (data or {}).get("targetId")
    try:
        moderation.ban(target_id, actor_id=sid)
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await _remove_player_from_room(target_id, room_id, "banned")
    return {"targetId": target_id, "banned": True}


@sio.on("room:moderation:unban")
async def room_moderation_unban(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    target_id = (data or {}).get("targetId")
    try:
        moderation.unban(target_id, actor_id=sid)
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return {"targetId": target_id, "banned": False}


@sio.on("room:moderation:report")
async def room_moderation_report(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    report = moderation.report_content(
        reporter_id=sid,
        target_type=data.get("targetType", "unknown"),
        target_id=data.get("targetId"),
        reason=data.get("reason", ""),
    )
    return report


@sio.on("room:moderation:reports:request")
async def room_moderation_reports_request(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    try:
        return moderation.list_reports(actor_id=sid)
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return


@sio.on("room:moderation:audit_log:request")
async def room_moderation_audit_log_request(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    try:
        return moderation.list_audit_log(actor_id=sid)
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return


@sio.on("room:moderation:external_links:set")
async def room_moderation_external_links_set(sid, data):
    room_id = rooms.get_player_room_id(sid)
    moderation = rooms.get_moderation(room_id) if room_id else None
    if not room_id or not moderation:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    allowed = bool((data or {}).get("allowed", True))
    try:
        moderation.set_external_links_allowed(allowed, actor_id=sid)
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    result = {"allowed": moderation.are_external_links_allowed()}
    await sio.emit("room:moderation:external_links", result, room=room_channel(room_id))
    return result


@sio.on("room:escape:configure")
async def room_escape_configure(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        builder.configure_escape_session(
            bool(data.get("enabled", False)), data["timeLimitMs"], briefing=data.get("briefing"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return True


@sio.on("room:escape:start")
async def room_escape_start(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    return builder.start_escape_session(sid, now_ms=time.time() * 1000)


@sio.on("room:escape:status")
async def room_escape_status(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    status = builder.get_escape_status(sid, now_ms=time.time() * 1000)
    return {**status, "briefing": builder.get_escape_briefing()}


@sio.on("room:escape:reset")
async def room_escape_reset(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    try:
        builder.reset_escape_session(sid)
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return True


@sio.on("room:escape:leaderboard:list")
async def room_escape_leaderboard_list(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    limit = (data or {}).get("limit", 10)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        limit = 10
    return builder.escape_leaderboard(limit)


@sio.on("room:puzzle:add")
async def room_puzzle_add(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        puzzle = builder.add_puzzle(
            data["puzzleId"], data["prompt"], data["answer"], hints=data.get("hints"),
            reveal_item_id=data.get("revealItemId"), unlock_door_id=data.get("unlockDoorId"),
            match_mode=data.get("matchMode", "exact"), max_attempts=data.get("maxAttempts"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return puzzle


@sio.on("room:puzzle:remove")
async def room_puzzle_remove(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        removed = builder.remove_puzzle(
            data["puzzleId"], requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except PermissionError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return
    if not removed:
        await sio.emit("error", {"message": "Unknown puzzle"}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return True


@sio.on("room:puzzle:list")
async def room_puzzle_list(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    return builder.list_puzzles()


@sio.on("room:puzzle:attempt")
async def room_puzzle_attempt(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        result = builder.attempt_solve_puzzle(
            data["puzzleId"], requester_id=sid, guess=data["guess"], now_ms=time.time() * 1000,
        )
    except KeyError as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return result


@sio.on("room:puzzle:hint")
async def room_puzzle_hint(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        result = builder.request_puzzle_hint(data["puzzleId"], requester_id=sid, now_ms=time.time() * 1000)
    except (KeyError, PermissionError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return result


@sio.on("room:puzzle:reset")
async def room_puzzle_reset(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        builder.reset_puzzle_attempts(
            data["puzzleId"], data["userId"], requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    return True


@sio.on("room:door:configure")
async def room_door_configure(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        door = builder.configure_door(
            data["objectId"], required_item_id=data.get("requiredItemId"),
            required_puzzle_ids=data.get("requiredPuzzleIds"), destination_tile=data.get("destinationTile"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return door


@sio.on("room:item:configure")
async def room_item_configure(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    data = data or {}
    try:
        item = builder.configure_item(
            data["objectId"], item_kind=data.get("itemKind"), single_use=data.get("singleUse"),
            requester_id=sid, is_room_host=_is_room_host(sid, room_id),
        )
    except (KeyError, PermissionError, ValueError) as exc:
        await sio.emit("error", {"message": str(exc)}, room=sid)
        return

    await broadcast_builder_state(room_id)
    return item


@sio.on("room:inventory:list")
async def room_inventory_list(sid, data):
    room_id, _tile, builder = _current_room_and_builder(sid)
    if not room_id:
        await sio.emit("error", {"message": "Join a room first"}, room=sid)
        return

    return builder.list_inventory(sid)


async def tick_escape_sessions(room_id: str, now_ms: float) -> None:
    """Expire any escape-room session that has run past its configured time
    limit (design doc §8.3), mirroring `tick_guided_tours`'s per-room,
    per-tick, try/except-wrapped shape so one broken room can never take
    down the shared game loop."""
    builder = rooms.get_builder(room_id)
    if builder is None:
        return
    try:
        expired_user_ids = builder.expire_escape_sessions(now_ms)
    except Exception:  # a broken tick must never take the whole game loop down
        logger.exception("escape session tick failed for room %s", room_id)
        return

    for user_id in expired_user_ids:
        await sio.emit("room:escape:expired", {"roomId": room_id}, room=user_id)


socket_app = socketio.ASGIApp(sio, app)


def main():
    uvicorn.run("server.main:socket_app", host="0.0.0.0", port=PORT, reload=False)


if __name__ == "__main__":
    main()
