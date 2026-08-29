import secrets
import time
from typing import Any

from server.game.moderation import ModerationState
from server.game.movement import clamp_position, create_position
from server.game.room import Room
from server.game.room_builder import RoomBuilderState
from server.game.room_styles import DEFAULT_ROOM_STYLE, is_valid_room_style, resolve_room_style
from server.game.tile_navigation import (
    can_add_neighbor_tile,
    detect_edge_transition,
    transition_to_neighbor,
)


class RoomsRegistry:
    """In-memory multi-room registry for create/list/join flows."""

    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.room_meta: dict[str, dict[str, Any]] = {}
        self.player_room: dict[str, str] = {}
        self.room_tiles: dict[str, set[tuple[int, int]]] = {}
        self.player_tile: dict[str, tuple[int, int]] = {}
        self.room_builders: dict[str, RoomBuilderState] = {}
        self.room_moderation: dict[str, ModerationState] = {}
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
        self.room_tiles[room_id] = {(0, 0)}
        self.room_builders[room_id] = RoomBuilderState()
        self.room_moderation[room_id] = ModerationState(owner_id="system")

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
        invite_code: str | None = None,
        room_style: str | None = None,
    ) -> dict[str, Any]:
        room_id = self._next_room_id()
        normalized_access = "invite" if access == "invite" else "public"
        self.rooms[room_id] = Room(room_id)
        self.room_meta[room_id] = {
            "id": room_id,
            "name": name,
            "hostId": host_id,
            "topicTags": topic_tags or [],
            "access": normalized_access,
            "maxUsers": max_users,
            "createdAtMs": int(time.time() * 1000),
            "inviteCode": invite_code if normalized_access == "invite" else None,
            "hostToken": secrets.token_urlsafe(24),
            "roomStyle": resolve_room_style(room_style),
        }
        self.room_tiles[room_id] = {(0, 0)}
        self.room_builders[room_id] = RoomBuilderState()
        self.room_moderation[room_id] = ModerationState(owner_id=host_id)
        return self.get_room_summary(room_id)

    def get_room(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id)

    def get_builder(self, room_id: str) -> RoomBuilderState | None:
        return self.room_builders.get(room_id)

    def get_moderation(self, room_id: str) -> ModerationState | None:
        return self.room_moderation.get(room_id)

    def global_escape_leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fastest escapes across every live room (design doc §14 Phase 3,
        resolving §16 Q4 in favour of a cross-room board).

        The registry is the only object that can see all rooms at once, so
        it owns the aggregation; each `EscapeSessionEngine` keeps knowing
        only about its own room. Every entry is annotated with its source
        room -- times from different rooms are not otherwise comparable.

        Like all other gameplay state this is in-memory only: the board is
        empty after a restart until new escapes are recorded. Persisting it
        is blocked on the same decision as the rest of §16.

        Iterates `self.rooms` (not `self.room_builders`) so a room removed
        from the registry stops contributing immediately.
        """
        effective_limit = limit if limit > 0 else 10
        entries: list[dict[str, Any]] = []
        for room_id in self.rooms:
            builder = self.room_builders.get(room_id)
            if builder is None:
                continue
            meta = self.room_meta.get(room_id, {})
            room_name = meta.get("name", room_id)
            for entry in builder.escape_leaderboard(limit=effective_limit):
                entries.append({**entry, "roomId": room_id, "roomName": room_name})
        entries.sort(key=lambda entry: entry["elapsedMs"])
        return entries[:effective_limit]

    def get_room_host_id(self, room_id: str) -> str | None:
        meta = self.room_meta.get(room_id)
        return meta.get("hostId") if meta else None

    def get_room_host_token(self, room_id: str) -> str | None:
        meta = self.room_meta.get(room_id)
        return meta.get("hostToken") if meta else None

    def get_room_style(self, room_id: str) -> str:
        meta = self.room_meta.get(room_id)
        return meta.get("roomStyle", DEFAULT_ROOM_STYLE) if meta else DEFAULT_ROOM_STYLE

    def set_room_style(
        self, room_id: str, style_id: str, requester_id: str | None = None, is_room_host: bool = False,
    ) -> str:
        """Change an existing room's ambient style after creation (design
        doc feature_designs/build_mode_ui_redesign_feature_design.md §11,
        §17 Decision D1). Room-host only, mirroring every other room-wide
        mutator's permission gate; raises KeyError for an unknown room and
        ValueError for a style id not in ROOM_STYLE_IDS."""
        meta = self.room_meta.get(room_id)
        if meta is None:
            raise KeyError(f"unknown room: {room_id}")
        if not is_room_host:
            raise PermissionError("only the room host can change the room style")
        if not is_valid_room_style(style_id):
            raise ValueError(f"invalid room style: {style_id}")
        meta["roomStyle"] = style_id
        return style_id

    def reclaim_host(self, room_id: str, new_player_id: str, host_token: str | None) -> bool:
        """Re-establish `new_player_id` as the owner/host of `room_id` if
        `host_token` matches the room's private host token (handed only to
        the original creator). Used so a room creator who reconnects with a
        new session id doesn't permanently lose ownership of their room."""
        meta = self.room_meta.get(room_id)
        if not meta or not host_token:
            return False
        expected_token = meta.get("hostToken")
        if not expected_token or not secrets.compare_digest(expected_token, host_token):
            return False
        meta["hostId"] = new_player_id
        moderation = self.room_moderation.get(room_id)
        if moderation:
            moderation.reassign_owner(new_player_id)
        return True

    def get_player_room_id(self, player_id: str) -> str | None:
        return self.player_room.get(player_id)

    def get_player_tile(self, player_id: str) -> tuple[int, int] | None:
        return self.player_tile.get(player_id)

    def get_room_tiles(self, room_id: str) -> list[dict[str, int]]:
        tiles = self.room_tiles.get(room_id, {(0, 0)})
        return [{"x": tx, "y": ty} for (tx, ty) in sorted(tiles, key=lambda t: (t[1], t[0]))]

    def get_room_summary(self, room_id: str) -> dict[str, Any] | None:
        meta = self.room_meta.get(room_id)
        room = self.rooms.get(room_id)
        if not meta or not room:
            return None
        topic_tags = meta.get("topicTags") or []
        return {
            "id": meta.get("id", room_id),
            "name": meta.get("name", room_id),
            "hostId": meta.get("hostId", "system"),
            "topicTags": topic_tags,
            "access": meta.get("access", "public"),
            "maxUsers": meta.get("maxUsers", 30),
            "createdAtMs": meta.get("createdAtMs", 0),
            "activeUsers": room.get_player_count(),
            "roomStyle": meta.get("roomStyle", DEFAULT_ROOM_STYLE),
        }

    def list_rooms(
        self,
        topic: str | None = None,
        access: str | None = None,
        sort_by: str = "newest",
    ) -> list[dict[str, Any]]:
        summaries = []
        for room_id in self.rooms.keys():
            summary = self.get_room_summary(room_id)
            if summary:
                summaries.append(summary)

        if topic:
            normalized_topic = topic.strip().lower()
            summaries = [
                room
                for room in summaries
                if normalized_topic in [tag.lower() for tag in room.get("topicTags", [])]
            ]

        if access in {"public", "invite"}:
            summaries = [room for room in summaries if room.get("access") == access]

        if sort_by == "active":
            return sorted(
                summaries,
                key=lambda r: (r.get("activeUsers", 0), r.get("createdAtMs", 0)),
                reverse=True,
            )

        return sorted(summaries, key=lambda r: r.get("createdAtMs", 0), reverse=True)

    def get_room_join_error(
        self,
        player_id: str,
        room_id: str,
        invite_code: str | None = None,
    ) -> str | None:
        room = self.rooms.get(room_id)
        meta = self.room_meta.get(room_id)
        if not room or not meta:
            return "not_found"

        current_room_id = self.player_room.get(player_id)
        if current_room_id == room_id:
            return None

        moderation = self.room_moderation.get(room_id)
        if moderation and moderation.is_banned(player_id):
            return "banned"

        if room.get_player_count() >= int(meta.get("maxUsers", 30)):
            return "full"

        if meta.get("access") == "invite":
            expected_code = meta.get("inviteCode")
            if expected_code and player_id != meta.get("hostId"):
                # Constant-time compare: a plain `!=` on a secret short code
                # leaks match length through timing, which is exactly the
                # signal needed to guess it character by character.
                supplied = invite_code if isinstance(invite_code, str) else ""
                if not secrets.compare_digest(supplied, str(expected_code)):
                    return "forbidden"

        return None

    def leave_current_room(self, player_id: str) -> None:
        current_room_id = self.player_room.get(player_id)
        if not current_room_id:
            return
        room = self.rooms.get(current_room_id)
        if room:
            room.remove_player(player_id)
        self.player_room.pop(player_id, None)
        self.player_tile.pop(player_id, None)

    def add_neighbor_tile(self, room_id: str, base_tile: tuple[int, int], direction: str) -> dict[str, int] | None:
        existing_tiles = self.room_tiles.get(room_id)
        if existing_tiles is None:
            return None
        if direction not in {"left", "right", "top", "bottom"}:
            return None
        if not can_add_neighbor_tile(existing_tiles, base_tile, direction):
            return None

        bx, by = base_tile
        if direction == "right":
            tile = (bx + 1, by)
        elif direction == "left":
            tile = (bx - 1, by)
        elif direction == "top":
            tile = (bx, by - 1)
        else:
            tile = (bx, by + 1)

        existing_tiles.add(tile)
        builder = self.room_builders.get(room_id)
        if builder is not None:
            builder.ensure_tile(tile)
        return {"x": tile[0], "y": tile[1]}

    def clone_tile(self, room_id: str, source: tuple[int, int], direction: str) -> dict[str, int] | None:
        builder = self.room_builders.get(room_id)
        existing_tiles = self.room_tiles.get(room_id)
        if builder is None or existing_tiles is None:
            return None
        cloned = builder.clone_tile(source, direction)
        if cloned is None:
            return None
        existing_tiles.add(cloned)
        return {"x": cloned[0], "y": cloned[1]}

    def delete_tile(self, room_id: str, coord: tuple[int, int]) -> bool:
        builder = self.room_builders.get(room_id)
        existing_tiles = self.room_tiles.get(room_id)
        if builder is None or existing_tiles is None:
            return False
        if not builder.delete_tile(coord):
            return False
        existing_tiles.discard(coord)
        return True

    def configure_tile(
        self,
        room_id: str,
        coord: tuple[int, int],
        label: str | None = None,
        purpose_tag: str | None = None,
        background_style: str | None = None,
        ambiance_style: str | None = None,
    ) -> bool:
        builder = self.room_builders.get(room_id)
        if builder is None:
            return False
        return builder.configure_tile(
            coord,
            label=label,
            purpose_tag=purpose_tag,
            background_style=background_style,
            ambiance_style=ambiance_style,
        )

    def transition_player_tile_if_needed(
        self,
        player_id: str,
        room_id: str,
        position: dict[str, float],
    ) -> dict[str, Any] | None:
        current_tile = self.player_tile.get(player_id, (0, 0))
        direction = detect_edge_transition(position)
        if not direction:
            return None

        try:
            next_result = transition_to_neighbor(
                {"x": current_tile[0], "y": current_tile[1]},
                position,
                direction,
            )
        except ValueError:
            return None
        next_tile_tuple = (next_result["tile"]["x"], next_result["tile"]["y"])
        room_tiles = self.room_tiles.get(room_id, {(0, 0)})
        if next_tile_tuple not in room_tiles:
            return None

        self.player_tile[player_id] = next_tile_tuple
        return next_result

    def warp_player_to_tile(
        self,
        player_id: str,
        room_id: str,
        destination_tile: tuple[int, int],
    ) -> dict[str, Any] | None:
        """Direct (non-adjacent) tile transition for an `escape_door`'s
        `destinationTile` (design doc §8.3). Unlike
        `transition_player_tile_if_needed`, the destination need not be an
        edge-adjacent neighbor of the player's current tile -- a door can
        link any two tiles the room author has placed. Returns the same
        {"tile": ..., "position": ...} shape as `transition_to_neighbor` so
        callers can treat both transition kinds identically; returns `None`
        if the destination tile doesn't exist in this room (defensive
        against a door authored with a stale/bad `destinationTile`)."""
        room_tiles = self.room_tiles.get(room_id, {(0, 0)})
        if destination_tile not in room_tiles:
            return None

        self.player_tile[player_id] = destination_tile
        return {
            "tile": {"x": destination_tile[0], "y": destination_tile[1]},
            "position": clamp_position(create_position()),
        }

    def join_room(
        self,
        player_id: str,
        avatar: dict[str, Any],
        room_id: str,
        invite_code: str | None = None,
    ) -> dict[str, Any] | None:
        room = self.rooms.get(room_id)
        if not room:
            return None

        join_error = self.get_room_join_error(player_id, room_id, invite_code=invite_code)
        if join_error:
            return None

        current_room_id = self.player_room.get(player_id)
        if current_room_id == room_id:
            existing = room.get_player(player_id)
            if existing:
                tile = self.player_tile.get(player_id, (0, 0))
                existing["tile"] = {"x": tile[0], "y": tile[1]}
                return existing
            player = room.add_player(player_id, avatar)
            self.player_tile[player_id] = (0, 0)
            player["tile"] = {"x": 0, "y": 0}
            return player

        self.leave_current_room(player_id)
        player = room.add_player(player_id, avatar)
        self.player_room[player_id] = room_id
        self.player_tile[player_id] = (0, 0)
        player["tile"] = {"x": 0, "y": 0}
        return player
