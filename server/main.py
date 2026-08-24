import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
    }


def all_players_payload() -> list[dict]:
    lobby = rooms.get_room("lobby")
    if not lobby:
        return []
    return [player_payload(p) for p in lobby.get_all_players()]


async def broadcast_room_state() -> None:
    await sio.emit("room:state", {"players": all_players_payload()})


async def broadcast_bubbles() -> None:
    lobby = rooms.get_room("lobby")
    if not lobby:
        return
    for player in lobby.get_all_players():
        bubbles = lobby.get_active_bubbles(player["id"])
        await sio.emit("chat:bubbles", bubbles, room=player["id"])


async def game_loop() -> None:
    interval  = 1.0 / TICK_RATE
    last_time = time.time()
    while True:
        await asyncio.sleep(interval)
        now      = time.time()
        now_ms   = now * 1000
        delta_ms = (now - last_time) * 1000
        last_time = now
        moved = False

        lobby = rooms.get_room("lobby")
        if not lobby:
            continue

        for player in lobby.get_all_players():
            # Regen stamina for everyone
            if player["id"] == BOT_ID:
                continue  # bot stamina managed in its own tick
            player["stamina"] = regen_stamina(player.get("stamina", 100), delta_ms)

            # Skip movement while stunned
            if now_ms < player.get("stunnedUntil", 0):
                continue

            direction = player.get("direction", {"x": 0, "y": 0})
            if direction["x"] != 0 or direction["y"] != 0:
                new_pos = move_by_direction(player["position"], direction, MOVE_SPEED)
                lobby.update_player_position(player["id"], new_pos)
                moved = True
                continue

            target = player.get("targetPosition")
            if target:
                new_pos = move_toward(player["position"], target, MOVE_SPEED)
                lobby.update_player_position(player["id"], new_pos)
                if new_pos["x"] == target["x"] and new_pos["y"] == target["y"]:
                    player["targetPosition"] = None
                    if player.get("pendingAction") is not None:
                        player["actionState"] = player["pendingAction"]
                        player["pendingAction"] = None
                moved = True

        # ── AI bot tick ───────────────────────────────────────────────────────
        all_players = lobby.get_all_players()
        bot_attack  = ai_bot.tick(now, all_players)

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
                    "attackerId":    BOT_ID,
                    "targetId":      bot_attack["targetId"],
                    "type":          bot_attack["type"],
                    "damage":        bot_attack["damage"],
                    "blocked":       bot_attack["blocked"],
                    "targetStamina": round(new_stamina),
                    "stunnedUntil":  stun_until,
                })
                moved = True

        # ── AI chat ───────────────────────────────────────────────────────────
        if ai_bot.pending_chat:
            msg = create_message(
                sender_id=BOT_ID,
                sender_name=BOT_AVATAR["username"],
                text=ai_bot.pending_chat,
                type="public",
            )
            lobby.add_message(msg)
            await sio.emit("chat:message", msg)
            ai_bot.pending_chat = None

        if moved:
            await broadcast_room_state()
        await broadcast_bubbles()


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
    rooms.leave_current_room(sid)
    await sio.emit("player:left", {"id": sid})


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

    await sio.emit(
        "player:joined",
        {"id": sid, "avatar": avatar, "position": player["position"]},
        room=sid,
    )
    await sio.emit("room:state", {"players": all_players_payload()}, room=sid)

    db_messages = await db.get_recent_messages("lobby", 50)
    visible = filter_messages_for_user(db_messages, sid)
    for msg in visible:
        lobby.add_message(msg)
    await sio.emit("chat:history", lobby.get_messages_for_player(sid), room=sid)

    await sio.emit(
        "player:entered",
        {"id": sid, "avatar": avatar, "position": player["position"]},
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

    await broadcast_room_state()


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
        await sio.emit("chat:message", message)
    else:
        await sio.emit("chat:message", message, room=sid)
        if recipient_id:
            await sio.emit("chat:message", message, room=recipient_id)

    await broadcast_bubbles()


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
    })
    await broadcast_room_state()


@sio.on("combat:block")
async def combat_block(sid, data):
    room_id = rooms.get_player_room_id(sid) or "lobby"
    room = rooms.get_room(room_id)
    if not room:
        return

    player = room.get_player(sid)
    if player:
        player["blocking"] = bool(data.get("blocking", False))


@sio.on("room:list")
async def room_list(sid):
    await sio.emit("room:list", {"rooms": rooms.list_rooms()}, room=sid)


@sio.on("room:create")
async def room_create(sid, data):
    room_name = (data.get("name") or "").strip()
    if not room_name:
        await sio.emit("error", {"message": "Room name is required"}, room=sid)
        return

    topic_tags = data.get("topicTags") or []
    access = data.get("access", "public")
    max_users = int(data.get("maxUsers", 30))
    room = rooms.create_room(
        host_id=sid,
        name=room_name,
        topic_tags=topic_tags,
        access=access,
        max_users=max_users,
    )
    await sio.emit("room:created", room, room=sid)
    await sio.emit("room:list", {"rooms": rooms.list_rooms()})


@sio.on("room:join")
async def room_join(sid, data):
    room_id = data.get("roomId")
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
    joined = rooms.join_room(sid, avatar, room_id)
    if not joined:
        await sio.emit("error", {"message": "Room not found"}, room=sid)
        return

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

    await sio.emit("room:joined", {"roomId": room_id}, room=sid)
    await sio.emit("room:list", {"rooms": rooms.list_rooms()})


socket_app = socketio.ASGIApp(sio, app)


def main():
    uvicorn.run("server.main:socket_app", host="0.0.0.0", port=PORT, reload=False)


if __name__ == "__main__":
    main()
