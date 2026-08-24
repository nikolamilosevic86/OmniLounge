import time
from typing import Any

from server.config import BUBBLE_DURATION_MS, MAX_MESSAGES
from server.game.chat import get_visible_messages, should_show_bubble
from server.game.movement import clamp_position, create_position


class Room:
    def __init__(self, room_id: str):
        self.id = room_id
        self.players: dict[str, dict[str, Any]] = {}
        self.messages: list[dict[str, Any]] = []

    def add_player(self, player_id: str, avatar: dict[str, Any]) -> dict[str, Any]:
        # Spread players across the left half of the room so they don't all stack
        import random
        x = random.uniform(120, 360)
        y = random.uniform(380, 480)
        player = {
            "id": player_id,
            "avatar": avatar,
            "position": create_position(x, y),
            "targetPosition": None,
            "direction": {"x": 0, "y": 0},
            "actionState": None,
            "pendingAction": None,
            # ── combat ──────────────────────────────────
            "stamina": 100.0,
            "blocking": False,
            "stunnedUntil": 0.0,
            "lastAttack": {"punch": 0.0, "kick": 0.0},
        }
        self.players[player_id] = player
        return player

    def remove_player(self, player_id: str) -> None:
        self.players.pop(player_id, None)

    def get_player(self, player_id: str) -> dict[str, Any] | None:
        return self.players.get(player_id)

    def get_player_count(self) -> int:
        return len(self.players)

    def get_all_players(self) -> list[dict[str, Any]]:
        return list(self.players.values())

    def update_player_position(self, player_id: str, position: dict[str, float]) -> dict[str, Any] | None:
        player = self.players.get(player_id)
        if not player:
            return None
        player["position"] = clamp_position(position)
        return player

    def set_player_target(self, player_id: str, target: dict[str, float], clear_action: bool = True) -> dict[str, Any] | None:
        player = self.players.get(player_id)
        if not player:
            return None
        player["targetPosition"] = clamp_position(target)
        player["direction"] = {"x": 0, "y": 0}
        if clear_action:
            player["actionState"] = None
            player["pendingAction"] = None
        return player

    def set_player_direction(self, player_id: str, direction: dict[str, float]) -> dict[str, Any] | None:
        player = self.players.get(player_id)
        if not player:
            return None
        player["direction"] = {
            "x": direction.get("x", 0),
            "y": direction.get("y", 0),
        }
        if direction.get("x", 0) != 0 or direction.get("y", 0) != 0:
            player["targetPosition"] = None
            player["actionState"] = None
            player["pendingAction"] = None
        return player

    def add_message(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        if len(self.messages) > MAX_MESSAGES:
            self.messages.pop(0)

    def get_messages(self) -> list[dict[str, Any]]:
        return list(self.messages)

    def get_messages_for_player(self, player_id: str) -> list[dict[str, Any]]:
        return get_visible_messages(self.messages, player_id)

    def get_active_bubbles(self, viewer_id: str) -> list[dict[str, Any]]:
        now = int(time.time() * 1000)
        latest_by_sender: dict[str, dict[str, Any]] = {}
        for msg in self.messages:
            if now - msg["timestamp"] >= BUBBLE_DURATION_MS:
                continue
            if not should_show_bubble(msg, viewer_id):
                continue
            latest_by_sender[msg["senderId"]] = {
                "senderId": msg["senderId"],
                "senderName": msg["senderName"],
                "text": msg["text"],
                "type": msg["type"],
                "timestamp": msg["timestamp"],
            }
        return list(latest_by_sender.values())
