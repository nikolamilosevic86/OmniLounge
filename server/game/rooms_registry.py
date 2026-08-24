import time
from typing import Any

from server.game.room import Room


class RoomsRegistry:
    """In-memory multi-room registry for create/list/join flows."""

    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.room_meta: dict[str, dict[str, Any]] = {}
        self.player_room: dict[str, str] = {}
        self._seq = 0
        self._create_lobby()

    def _create_lobby(self) -> None:
        room_id = "lobby"
        self.rooms[room_id] = Room(room_id)
        self.room_meta[room_id] = {
            "id": room_id,
            "name": "Lobby",
            "hostId": "system",
            "topicTags": ["social"],
            "access": "public",
            "maxUsers": 200,
            "createdAtMs": int(time.time() * 1000),
        }

    def _next_room_id(self) -> str:
        self._seq += 1
        return f"room-{self._seq:04d}"

    def create_room(
        self,
        host_id: str,
        name: str,
        topic_tags: list[str] | None = None,
        access: str = "public",
        max_users: int = 30,
    ) -> dict[str, Any]:
        room_id = self._next_room_id()
        self.rooms[room_id] = Room(room_id)
        self.room_meta[room_id] = {
            "id": room_id,
            "name": name,
            "hostId": host_id,
            "topicTags": topic_tags or [],
            "access": access,
            "maxUsers": max_users,
            "createdAtMs": int(time.time() * 1000),
        }
        return self.get_room_summary(room_id)

    def get_room(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id)

    def get_player_room_id(self, player_id: str) -> str | None:
        return self.player_room.get(player_id)

    def get_room_summary(self, room_id: str) -> dict[str, Any] | None:
        meta = self.room_meta.get(room_id)
        room = self.rooms.get(room_id)
        if not meta or not room:
            return None
        return {
            **meta,
            "activeUsers": room.get_player_count(),
        }

    def list_rooms(self) -> list[dict[str, Any]]:
        summaries = []
        for room_id in self.rooms.keys():
            summary = self.get_room_summary(room_id)
            if summary:
                summaries.append(summary)
        return sorted(summaries, key=lambda r: r["createdAtMs"], reverse=True)

    def leave_current_room(self, player_id: str) -> None:
        current_room_id = self.player_room.get(player_id)
        if not current_room_id:
            return
        room = self.rooms.get(current_room_id)
        if room:
            room.remove_player(player_id)
        self.player_room.pop(player_id, None)

    def join_room(self, player_id: str, avatar: dict[str, Any], room_id: str) -> dict[str, Any] | None:
        room = self.rooms.get(room_id)
        if not room:
            return None

        current_room_id = self.player_room.get(player_id)
        if current_room_id == room_id:
            existing = room.get_player(player_id)
            return existing if existing else room.add_player(player_id, avatar)

        self.leave_current_room(player_id)
        player = room.add_player(player_id, avatar)
        self.player_room[player_id] = room_id
        return player
