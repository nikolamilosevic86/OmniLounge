"""Phase D: Depth-first room builder domain logic.

Pure, in-memory, per-room state container used by the room builder UI
(build mode). Mirrors the object/tile/zone/trigger/version fields defined
in `server/db/schema.sql` and validated by `room_builder_models.py`, but
keeps game/authoring logic independent of persistence so it can be unit
tested without a database.
"""

from typing import Any, Literal

from server.game.bookshelf import BookshelfLibrary
from server.game.escape_session import EscapeSessionEngine
from server.game.inventory import InventoryEngine
from server.game.media import MediaLibrary
from server.game.npc_guide import GuideEngine
from server.game.puzzle import PuzzleEngine
from server.game.room_builder_models import BoundsModel, RoomObjectPlacementModel
from server.game.room_object_catalog import (
    COLOR_PRESETS,
    MATERIAL_PRESETS,
    get_catalog_entry,
    get_interaction_menu,
    resolve_size_preset,
)
from server.game.story import (
    DEFAULT_CHARACTER_NAME,
    DEFAULT_CHARACTER_ROLE,
    DEFAULT_CHARACTER_START_NODE_ID,
    StoryEngine,
)
from server.game.tile_navigation import can_add_neighbor_tile

ZoneType = Literal["collision", "interaction"]

_VALID_ZONE_TYPES = {"collision", "interaction"}

# Phase J performance budget: caps how many objects a single tile can hold so
# a tile's render/interaction cost stays bounded (avoids the canvas and
# builder UI degrading from an unbounded number of objects on one screen).
MAX_OBJECTS_PER_TILE = 40


def _neighbor_coord(base: tuple[int, int], direction: str) -> tuple[int, int]:
    bx, by = base
    if direction == "right":
        return bx + 1, by
    if direction == "left":
        return bx - 1, by
    if direction == "top":
        return bx, by - 1
    if direction == "bottom":
        return bx, by + 1
    raise ValueError(f"invalid direction: {direction}")


class RoomBuilderState:
    """Authoring-time state for a single room: tiles, objects, zones,
    scripted triggers, and draft/publish version history."""

    def __init__(self) -> None:
        self._tiles: dict[tuple[int, int], dict[str, Any]] = {
            (0, 0): self._make_tile_record(is_spawn=True)
        }
        self._objects: dict[str, dict[str, Any]] = {}
        self._zones: dict[str, dict[str, Any]] = {}
        self._triggers: dict[str, dict[str, Any]] = {}
        self._trigger_inside_state: dict[tuple[str, str], bool] = {}
        self._trigger_last_fired_ms: dict[tuple[str, str], float] = {}
        self._trigger_fired_ever: set[tuple[str, str]] = set()
        self._interaction_last_ms: dict[tuple[str, str, str], float] = {}
        self._bookshelf = BookshelfLibrary()
        self._media = MediaLibrary()
        self._story = StoryEngine()
        self._guide = GuideEngine()
        # Escape room feature (feature_designs/escape_room_feature_design.md
        # §14): one instance per room, owned exactly like every other
        # per-room engine above.
        self._puzzles = PuzzleEngine()
        self._inventory = InventoryEngine()
        self._escape = EscapeSessionEngine()
        self._versions: list[dict[str, Any]] = []
        self._active_version: int | None = None
        self._next_version = 1

    # ── Tile graph editor ────────────────────────────────────────────────

    @staticmethod
    def _make_tile_record(is_spawn: bool = False) -> dict[str, Any]:
        return {
            "label": None,
            "purposeTag": None,
            "backgroundStyle": None,
            "ambianceStyle": None,
            "isSpawn": is_spawn,
        }

    def get_tile(self, coord: tuple[int, int]) -> dict[str, Any] | None:
        record = self._tiles.get(coord)
        if record is None:
            return None
        return {"x": coord[0], "y": coord[1], **record}

    def ensure_tile(self, coord: tuple[int, int]) -> None:
        """Register a tile coordinate created outside the builder (e.g. via
        the plain navigation add-neighbor flow) without clobbering any
        existing visual configuration for that coordinate."""
        if coord not in self._tiles:
            self._tiles[coord] = self._make_tile_record()

    def list_tiles(self) -> list[dict[str, Any]]:
        return [
            {"x": x, "y": y, **record}
            for (x, y), record in sorted(self._tiles.items(), key=lambda item: (item[0][1], item[0][0]))
        ]

    def add_tile(self, base: tuple[int, int], direction: str) -> tuple[int, int] | None:
        existing = set(self._tiles.keys())
        if not can_add_neighbor_tile(existing, base, direction):
            return None
        coord = _neighbor_coord(base, direction)
        self._tiles[coord] = self._make_tile_record()
        return coord

    def clone_tile(self, source: tuple[int, int], direction: str) -> tuple[int, int] | None:
        source_record = self._tiles.get(source)
        if source_record is None:
            return None
        existing = set(self._tiles.keys())
        if not can_add_neighbor_tile(existing, source, direction):
            return None
        coord = _neighbor_coord(source, direction)
        clone = dict(source_record)
        clone["isSpawn"] = False
        self._tiles[coord] = clone
        return coord

    def delete_tile(self, coord: tuple[int, int]) -> bool:
        record = self._tiles.get(coord)
        if record is None:
            return False
        if record["isSpawn"]:
            return False
        if any(obj["tile"] == coord for obj in self._objects.values()):
            return False
        del self._tiles[coord]
        return True

    def configure_tile(
        self,
        coord: tuple[int, int],
        label: str | None = None,
        purpose_tag: str | None = None,
        background_style: str | None = None,
        ambiance_style: str | None = None,
    ) -> bool:
        record = self._tiles.get(coord)
        if record is None:
            return False
        if label is not None:
            record["label"] = label
        if purpose_tag is not None:
            record["purposeTag"] = purpose_tag
        if background_style is not None:
            record["backgroundStyle"] = background_style
        if ambiance_style is not None:
            record["ambianceStyle"] = ambiance_style
        return True

    # ── Object placement tools ───────────────────────────────────────────

    def _next_z_index(self) -> int:
        if not self._objects:
            return 0
        return max(obj["zIndex"] for obj in self._objects.values()) + 1

    def _object_count_on_tile(self, tile: tuple[int, int]) -> int:
        return sum(1 for obj in self._objects.values() if obj["tile"] == tile)

    def _check_tile_object_budget(self, tile: tuple[int, int]) -> None:
        if self._object_count_on_tile(tile) >= MAX_OBJECTS_PER_TILE:
            raise ValueError(
                f"tile object budget exceeded: tile {tile} already has {MAX_OBJECTS_PER_TILE} objects"
            )

    def create_object(
        self,
        object_id: str,
        object_type: str,
        tile: tuple[int, int],
        x: float,
        y: float,
        width: float | None = None,
        height: float | None = None,
        size_preset: str | None = None,
        rotation: float = 0.0,
        interaction_radius: float = 20.0,
        color: str | None = None,
        material: str | None = None,
        edit_permission: str = "owner_only",
        interaction_cooldown_ms: float = 0.0,
        created_by: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if tile not in self._tiles:
            raise ValueError(f"unknown tile: {tile}")
        self._check_tile_object_budget(tile)

        if width is None or height is None:
            preset = size_preset or get_catalog_entry(object_type)["defaultSizePreset"]
            preset_width, preset_height = resolve_size_preset(object_type, preset)
            width = preset_width if width is None else width
            height = preset_height if height is None else height
            size_preset = preset
        elif size_preset is not None:
            resolve_size_preset(object_type, size_preset)  # validate preset name/type pair

        validated = RoomObjectPlacementModel(
            object_id=object_id,
            object_type=object_type,
            tile_x=tile[0],
            tile_y=tile[1],
            x=x,
            y=y,
            width=width,
            height=height,
            rotation=rotation,
            z_index=self._next_z_index(),
            is_locked=False,
            interaction_radius=interaction_radius,
            size_preset=size_preset,
            color=color,
            material=material,
            edit_permission=edit_permission,
            interaction_cooldown_ms=interaction_cooldown_ms,
        )

        record = {
            "objectId": validated.object_id,
            "objectType": validated.object_type,
            "tile": tile,
            "x": validated.x,
            "y": validated.y,
            "width": validated.width,
            "height": validated.height,
            "rotation": validated.rotation % 360,
            "zIndex": validated.z_index,
            "isLocked": validated.is_locked,
            "interactionRadius": validated.interaction_radius,
            "sizePreset": validated.size_preset,
            "color": validated.color,
            "material": validated.material,
            "editPermission": validated.edit_permission,
            "interactionCooldownMs": validated.interaction_cooldown_ms,
            "isInteractable": True,
            "createdBy": created_by,
            "config": config or {},
        }
        self._objects[object_id] = record
        if record["objectType"] == "ai_character":
            # Provision the story character up front. Every character editor
            # action (appearance, knowledge base, generative mode) resolves a
            # character record, so without this they all fail with "unknown
            # character" until the author happens to save a name first.
            self._story.add_character(
                object_id, object_id,
                name=DEFAULT_CHARACTER_NAME,
                role=DEFAULT_CHARACTER_ROLE,
                start_node_id=DEFAULT_CHARACTER_START_NODE_ID,
            )
        return dict(record)

    def _interactions_for(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        if not record["isInteractable"]:
            return []
        menu = get_interaction_menu(record["objectType"])
        if record["config"].get("puzzleId"):
            # Any object type can double as a puzzle prop (design doc §6.2)
            # -- appended onto (not instead of) the type's static menu, and
            # only for instances actually bound to a puzzle.
            menu.append({"interactionType": "solve_puzzle", "label": "Solve", "actionState": None})
        return menu

    def _decorate_object(self, record: dict[str, Any]) -> dict[str, Any]:
        decorated = {**record, "interactions": self._interactions_for(record)}
        if record["objectType"] == "ai_character":
            # Embed the character's name/appearance directly on the object so
            # every client in the room (not just whoever is editing it) can
            # render the AI character in the avatar's shape, with its
            # configured look, without a separate round-trip.
            decorated["character"] = self._story.get_character(record["objectId"], record["objectId"])
            # Learners need to know a character can give a guided tour (to
            # offer "follow me") without being able to edit it, so the route
            # and any in-progress tour ship with the object too.
            decorated["waypoints"] = self._guide.list_waypoints(record["objectId"])
            decorated["tour"] = self._guide.public_tour(record["objectId"])
        return decorated

    def get_object(self, object_id: str) -> dict[str, Any] | None:
        record = self._objects.get(object_id)
        if record is None:
            return None
        return self._decorate_object(record)

    def list_objects(
        self, tile: tuple[int, int] | None = None,
        requester_id: str | None = None, is_room_host: bool = False,
    ) -> list[dict[str, Any]]:
        objects = self._objects.values()
        if tile is not None:
            objects = [o for o in objects if o["tile"] == tile]
        objects = [o for o in objects if self._is_visible_to(o, requester_id, is_room_host)]
        return [self._decorate_object(o) for o in sorted(objects, key=lambda o: o["zIndex"])]

    def list_objects_for_tiles(
        self, tiles: set[tuple[int, int]],
        requester_id: str | None = None, is_room_host: bool = False,
    ) -> list[dict[str, Any]]:
        """Like `list_objects`, but scoped to any tile in `tiles`. Used to
        lazily load only the objects near a client instead of the whole
        room, which matters once a room has many tiles/objects."""
        objects = [o for o in self._objects.values() if o["tile"] in tiles]
        objects = [o for o in objects if self._is_visible_to(o, requester_id, is_room_host)]
        return [self._decorate_object(o) for o in sorted(objects, key=lambda o: o["zIndex"])]

    def _is_visible_to(
        self, record: dict[str, Any], requester_id: str | None, is_room_host: bool
    ) -> bool:
        """An unrevealed `hidden_item` must never be sent to a visitor's
        client at all (design doc §5.2) -- not filtered client-side, since a
        visitor could otherwise discover its position from network traffic
        before solving anything. Every other object type is always visible.
        `is_room_host` (build-mode) always sees everything so authors can
        find and edit hidden items. `requester_id is None` means a trusted
        internal caller (server-side migrations, tests) with no specific
        visitor in mind, matching the same convention `_can_edit` uses."""
        if is_room_host or requester_id is None:
            return True
        if record["objectType"] != "hidden_item":
            return True
        object_id = record["objectId"]
        if self._inventory.has(requester_id, object_id):
            if record["config"].get("singleUse", True):
                return False  # already picked up -- would look duplicated in their own view
            return True  # singleUse=False items remain re-visible/re-collectible after pickup
        return self._escape.has_revealed(requester_id, object_id)

    def _require_object(self, object_id: str) -> dict[str, Any]:
        record = self._objects.get(object_id)
        if record is None:
            raise KeyError(f"unknown object: {object_id}")
        return record

    def _require_unlocked(self, record: dict[str, Any]) -> None:
        if record["isLocked"]:
            raise PermissionError(f"object {record['objectId']} is locked")

    def _can_edit(self, record: dict[str, Any], requester_id: str | None, is_room_host: bool) -> bool:
        if requester_id is None:
            return True  # trusted/internal call (e.g. server-side migrations, tests)
        if is_room_host:
            return True
        if record["editPermission"] == "anyone":
            return True
        return requester_id == record["createdBy"]

    def _require_edit_permission(
        self, record: dict[str, Any], requester_id: str | None, is_room_host: bool
    ) -> None:
        if not self._can_edit(record, requester_id, is_room_host):
            raise PermissionError(f"object {record['objectId']} cannot be edited by this user")

    @staticmethod
    def _require_numeric(value: Any, field_name: str) -> float:
        """Reject non-numeric client input before it is stored in shared
        room state or used in an arithmetic/comparison expression. Unlike
        `create_object` (which validates through `RoomObjectPlacementModel`),
        move/resize/rotate take raw numeric args directly from socket
        handlers, so a malicious client could otherwise send a string
        (silently corrupting broadcast state, e.g. `move_object`) or trigger
        an uncaught `TypeError` (e.g. `"x" <= 0` in `resize_object`, or a
        string running through the `%` operator in `rotate_object`)."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} must be numeric, got {value!r}")
        return value

    def move_object(
        self, object_id: str, x: float, y: float, requester_id: str | None = None, is_room_host: bool = False
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        self._require_unlocked(record)
        x = self._require_numeric(x, "x")
        y = self._require_numeric(y, "y")
        record["x"] = x
        record["y"] = y
        return dict(record)

    def resize_object(
        self,
        object_id: str,
        width: float,
        height: float,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        self._require_unlocked(record)
        width = self._require_numeric(width, "width")
        height = self._require_numeric(height, "height")
        if width <= 0 or height <= 0:
            raise ValueError("geometry dimensions must be positive")
        record["width"] = width
        record["height"] = height
        record["sizePreset"] = None  # no longer matches a named preset
        return dict(record)

    def rotate_object(
        self, object_id: str, rotation: float, requester_id: str | None = None, is_room_host: bool = False
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        self._require_unlocked(record)
        rotation = self._require_numeric(rotation, "rotation")
        record["rotation"] = rotation % 360
        return dict(record)

    def set_object_style(
        self,
        object_id: str,
        color: str | None = None,
        material: str | None = None,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        if color is not None:
            if color not in COLOR_PRESETS:
                raise ValueError(f"unknown color preset: {color}")
            record["color"] = color
        if material is not None:
            if material not in MATERIAL_PRESETS:
                raise ValueError(f"unknown material preset: {material}")
            record["material"] = material
        return dict(record)

    def set_object_size_preset(
        self,
        object_id: str,
        size_preset: str,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        width, height = resolve_size_preset(record["objectType"], size_preset)
        record["sizePreset"] = size_preset
        record["width"] = width
        record["height"] = height
        return dict(record)

    def set_object_edit_permission(
        self,
        object_id: str,
        edit_permission: str,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> dict[str, Any]:
        if edit_permission not in {"owner_only", "anyone"}:
            raise ValueError(f"invalid edit permission: {edit_permission}")
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        record["editPermission"] = edit_permission
        return dict(record)

    def set_object_interactable(
        self,
        object_id: str,
        interactable: bool,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        record["isInteractable"] = bool(interactable)
        return dict(record)

    def duplicate_object(
        self,
        object_id: str,
        new_object_id: str,
        offset: tuple[float, float] = (16.0, 16.0),
        requester_id: str | None = None,
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        if new_object_id in self._objects:
            raise ValueError(f"object id already exists: {new_object_id}")
        self._check_tile_object_budget(record["tile"])
        clone = dict(record)
        clone["objectId"] = new_object_id
        clone["x"] = record["x"] + offset[0]
        clone["y"] = record["y"] + offset[1]
        clone["isLocked"] = False
        clone["zIndex"] = self._next_z_index()
        clone["config"] = dict(record["config"])
        clone["createdBy"] = requester_id if requester_id is not None else record["createdBy"]
        self._objects[new_object_id] = clone
        return dict(clone)

    def get_object_interaction_menu(self, object_id: str) -> list[dict[str, Any]]:
        record = self._require_object(object_id)
        return self._interactions_for(record)

    def _require_bookshelf(self, object_id: str) -> dict[str, Any]:
        record = self._require_object(object_id)
        if record["objectType"] != "bookshelf":
            raise ValueError(f"object {object_id} is not a bookshelf")
        return record

    def add_book(
        self,
        object_id: str,
        book_id: str,
        title: str,
        content_body: str,
        author: str | None = None,
        summary: str | None = None,
        reading_level: str | None = None,
        content_type: str = "inline",
        est_read_minutes: int | None = None,
        cover_url: str | None = None,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_bookshelf(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._bookshelf.add_book(
            object_id, book_id, title=title, content_body=content_body, author=author,
            summary=summary, reading_level=reading_level, content_type=content_type,
            est_read_minutes=est_read_minutes, cover_url=cover_url,
        )

    def remove_book(
        self, object_id: str, book_id: str, requester_id: str | None = None, is_room_host: bool = False
    ) -> bool:
        record = self._require_bookshelf(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._bookshelf.remove_book(object_id, book_id)

    def list_books(self, object_id: str) -> list[dict[str, Any]]:
        self._require_bookshelf(object_id)
        return self._bookshelf.list_books(object_id)

    def save_reading_progress(
        self, object_id: str, book_id: str, user_id: str, progress: float, now_ms: float
    ) -> dict[str, Any]:
        self._require_bookshelf(object_id)
        return self._bookshelf.save_progress(object_id, book_id, user_id, progress, now_ms)

    def get_reading_progress(self, object_id: str, book_id: str, user_id: str) -> dict[str, Any] | None:
        self._require_bookshelf(object_id)
        return self._bookshelf.get_progress(object_id, book_id, user_id)

    def _require_tv(self, object_id: str) -> dict[str, Any]:
        record = self._require_object(object_id)
        if record["objectType"] != "tv":
            raise ValueError(f"object {object_id} is not a tv")
        return record

    def _require_music_player(self, object_id: str) -> dict[str, Any]:
        record = self._require_object(object_id)
        if record["objectType"] != "music_player":
            raise ValueError(f"object {object_id} is not a music_player")
        return record

    def _require_media_object(self, object_id: str) -> dict[str, Any]:
        record = self._require_object(object_id)
        if record["objectType"] not in ("tv", "music_player"):
            raise ValueError(f"object {object_id} does not support media playback")
        return record

    def add_video(
        self, object_id: str, video_id: str, title: str, youtube_video_id: str,
        description: str | None = None, requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_tv(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._media.add_video(
            object_id, video_id, title=title, youtube_video_id=youtube_video_id, description=description,
        )

    def remove_video(
        self, object_id: str, video_id: str, requester_id: str | None = None, is_room_host: bool = False,
    ) -> bool:
        record = self._require_tv(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._media.remove_video(object_id, video_id)

    def list_videos(self, object_id: str) -> list[dict[str, Any]]:
        self._require_tv(object_id)
        return self._media.list_videos(object_id)

    def add_track(
        self, object_id: str, track_id: str, title: str, youtube_video_id: str,
        artist: str | None = None, duration_seconds: int | None = None,
        requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_music_player(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._media.add_track(
            object_id, track_id, title=title, youtube_video_id=youtube_video_id,
            artist=artist, duration_seconds=duration_seconds,
        )

    def remove_track(
        self, object_id: str, track_id: str, requester_id: str | None = None, is_room_host: bool = False,
    ) -> bool:
        record = self._require_music_player(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._media.remove_track(object_id, track_id)

    def list_tracks(self, object_id: str) -> list[dict[str, Any]]:
        self._require_music_player(object_id)
        return self._media.list_tracks(object_id)

    def _require_media_item_exists(self, record: dict[str, Any], item_id: str) -> None:
        if record["objectType"] == "tv":
            if self._media.get_video(record["objectId"], item_id) is None:
                raise KeyError(f"unknown video: {item_id}")
        else:
            if self._media.get_track(record["objectId"], item_id) is None:
                raise KeyError(f"unknown track: {item_id}")

    def start_watch_sync(self, object_id: str, host_id: str, item_id: str, now_ms: float) -> dict[str, Any]:
        record = self._require_media_object(object_id)
        self._require_media_item_exists(record, item_id)
        return self._media.start_sync_session(object_id, host_id=host_id, item_id=item_id, now_ms=now_ms)

    def join_watch_sync(self, object_id: str, user_id: str) -> dict[str, Any]:
        self._require_media_object(object_id)
        return self._media.join_sync_session(object_id, user_id=user_id)

    def leave_watch_sync(self, object_id: str, user_id: str) -> None:
        self._require_media_object(object_id)
        self._media.leave_sync_session(object_id, user_id=user_id)

    def update_watch_sync(
        self, object_id: str, requester_id: str, is_playing: bool, position_seconds: float, now_ms: float,
    ) -> dict[str, Any]:
        self._require_media_object(object_id)
        return self._media.update_playback(
            object_id, requester_id=requester_id, is_playing=is_playing,
            position_seconds=position_seconds, now_ms=now_ms,
        )

    def end_watch_sync(self, object_id: str, requester_id: str) -> bool:
        self._require_media_object(object_id)
        return self._media.end_sync_session(object_id, requester_id=requester_id)

    def get_watch_sync(self, object_id: str, now_ms: float) -> dict[str, Any] | None:
        self._require_media_object(object_id)
        return self._media.get_sync_session(object_id, now_ms=now_ms)

    def _require_ai_character(self, object_id: str) -> dict[str, Any]:
        record = self._require_object(object_id)
        if record["objectType"] != "ai_character":
            raise ValueError(f"object {object_id} is not an ai_character")
        return record

    def configure_character(
        self, object_id: str, name: str, role: str, start_node_id: str, portrait_url: str | None = None,
        requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        if self._story.get_character(object_id, object_id) is None:
            return self._story.add_character(
                object_id, object_id, name=name, role=role, start_node_id=start_node_id,
                portrait_url=portrait_url,
            )
        return self._story.set_character_profile(
            object_id, object_id, name=name, role=role, start_node_id=start_node_id,
            portrait_url=portrait_url,
        )

    def configure_character_appearance(
        self, object_id: str, appearance: dict[str, Any],
        requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._story.set_character_appearance(object_id, object_id, appearance)

    def get_character_config(self, object_id: str) -> dict[str, Any] | None:
        self._require_ai_character(object_id)
        return self._story.get_character(object_id, object_id)

    def set_character_knowledge_base_title(
        self, object_id: str, title: str | None, requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._story.set_knowledge_base_title(object_id, object_id, title)

    def add_character_knowledge_document(
        self, object_id: str, doc_id: str, title: str, doc_type: str, content: str | None = None,
        url: str | None = None, requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._story.add_knowledge_document(
            object_id, object_id, doc_id, title, doc_type, content=content, url=url,
        )

    def remove_character_knowledge_document(
        self, object_id: str, doc_id: str, requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._story.remove_knowledge_document(object_id, object_id, doc_id)

    def update_character_knowledge_document(
        self, object_id: str, doc_id: str, title: str, doc_type: str, content: str | None = None,
        url: str | None = None, requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._story.update_knowledge_document(
            object_id, object_id, doc_id, title, doc_type, content=content, url=url,
        )

    def move_character_knowledge_document(
        self, object_id: str, doc_id: str, direction: str, requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._story.move_knowledge_document(object_id, object_id, doc_id, direction)

    def configure_character_generative_mode(
        self, object_id: str, api_base_url: str | None = None, api_key: str | None = None,
        requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        self._require_ai_character(object_id)
        # Phase I: AI API settings are restricted to the room admin (host),
        # not the general object-level edit permission (which would also
        # allow the character's creator even if they aren't the room admin).
        if not is_room_host:
            raise PermissionError("only the room admin can manage AI API settings")
        return self._story.configure_generative_mode(object_id, object_id, api_base_url=api_base_url, api_key=api_key)

    def add_story_node(
        self, object_id: str, node_id: str, character_line: str, choices: list[dict[str, Any]] | None = None,
        completion_flag: bool = False, knowledge_check: str | None = None,
        requester_id: str | None = None, is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._story.add_story_node(
            object_id, object_id, node_id, character_line=character_line, choices=choices,
            completion_flag=completion_flag, knowledge_check=knowledge_check,
        )

    def list_story_nodes(self, object_id: str) -> list[dict[str, Any]]:
        self._require_ai_character(object_id)
        return self._story.list_story_nodes(object_id, object_id)

    def talk_to_character(
        self, object_id: str, requester_id: str, choice_index: int | None = None,
    ) -> dict[str, Any]:
        self._require_ai_character(object_id)
        return self._story.talk(
            object_id, object_id, user_id=requester_id, choice_index=choice_index,
            is_solved=self._puzzles.is_solved,
        )

    def restart_character_story(self, object_id: str, requester_id: str) -> dict[str, Any]:
        self._require_ai_character(object_id)
        return self._story.restart_story(object_id, object_id, user_id=requester_id)

    def ask_character(
        self, object_id: str, requester_id: str, user_message: str, caller: Any, now_ms: float = 0.0,
    ) -> dict[str, Any]:
        self._require_ai_character(object_id)
        return self._story.ask_generative(
            object_id, object_id, user_message, caller=caller, user_id=requester_id, now_ms=now_ms,
        )

    # ── AI character guided tours ("follow me") ──────────────────────────

    def add_character_waypoint(
        self, object_id: str, waypoint_id: str, x: float, y: float, label: str | None = None,
        requester_id: str | None = None, is_room_host: bool = False,
    ) -> list[dict[str, Any]]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._guide.add_waypoint(object_id, waypoint_id, x, y, label)

    def remove_character_waypoint(
        self, object_id: str, waypoint_id: str, requester_id: str | None = None, is_room_host: bool = False,
    ) -> list[dict[str, Any]]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._guide.remove_waypoint(object_id, waypoint_id)

    def move_character_waypoint(
        self, object_id: str, waypoint_id: str, direction: str,
        requester_id: str | None = None, is_room_host: bool = False,
    ) -> list[dict[str, Any]]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._guide.move_waypoint(object_id, waypoint_id, direction)

    def clear_character_waypoints(
        self, object_id: str, requester_id: str | None = None, is_room_host: bool = False,
    ) -> list[dict[str, Any]]:
        record = self._require_ai_character(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        return self._guide.clear_waypoints(object_id)

    def list_character_waypoints(self, object_id: str) -> list[dict[str, Any]]:
        self._require_ai_character(object_id)
        return self._guide.list_waypoints(object_id)

    def start_character_tour(
        self, object_id: str, requester_id: str, now_ms: float = 0.0,
    ) -> dict[str, Any]:
        """Accept a character's "follow me" invitation. Anyone in the room
        may do this -- it is a learner-facing action, not an authoring one,
        so unlike the route editor it is deliberately not permission-gated."""
        record = self._require_ai_character(object_id)
        return self._guide.start_tour(
            object_id, origin={"x": record["x"], "y": record["y"]},
            follower_id=requester_id, now_ms=now_ms,
        )

    def stop_character_tour(self, object_id: str, requester_id: str) -> dict[str, Any] | None:
        self._require_ai_character(object_id)
        return self._guide.leave_tour(object_id, requester_id)

    def get_character_tour(self, object_id: str) -> dict[str, Any] | None:
        self._require_ai_character(object_id)
        return self._guide.public_tour(object_id)

    def tick_character_tours(self, now_ms: float) -> list[dict[str, Any]]:
        """Advance every in-progress guided tour in this room by one game
        tick, writing each character's new position back onto its room
        object so it is picked up by collision, hit-testing and the normal
        builder-state broadcast. Returns one result per moving character for
        the caller to broadcast."""
        results = []
        for object_id in self._guide.active_object_ids():
            record = self._objects.get(object_id)
            if record is None:
                self._guide.discard(object_id)
                continue
            result = self._guide.tick(object_id, {"x": record["x"], "y": record["y"]}, now_ms)
            if result is None:
                continue
            if result["moved"]:
                record["x"] = result["position"]["x"]
                record["y"] = result["position"]["y"]
            character = self._story.get_character(object_id, object_id)
            result["tile"] = record["tile"]
            result["characterName"] = (character or {}).get("name") or "AI Character"
            results.append(result)
        return results

    def interact_with_object(
        self, object_id: str, interaction_type: str, requester_id: str, now_ms: float,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        if not record["isInteractable"]:
            raise PermissionError(f"object {object_id} is not interactable")

        menu_entry = next(
            (item for item in self._interactions_for(record) if item["interactionType"] == interaction_type),
            None,
        )
        if menu_entry is None:
            raise ValueError(f"unsupported interaction for {record['objectType']}: {interaction_type}")

        cooldown_ms = record["interactionCooldownMs"]
        if cooldown_ms > 0:
            key = (object_id, requester_id, interaction_type)
            last_fired = self._interaction_last_ms.get(key)
            if last_fired is not None and (now_ms - last_fired) < cooldown_ms:
                raise PermissionError("interaction is on cooldown")
            self._interaction_last_ms[key] = now_ms

        payload = self._interaction_payload(record, interaction_type, requester_id, now_ms, display_name)

        return {
            "objectId": object_id,
            "objectType": record["objectType"],
            "interactionType": menu_entry["interactionType"],
            "label": menu_entry["label"],
            "actionState": menu_entry.get("actionState"),
            "payload": payload,
        }

    def _interaction_payload(
        self, record: dict[str, Any], interaction_type: str, requester_id: str, now_ms: float,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        object_id = record["objectId"]
        if interaction_type == "solve_puzzle":
            # Reachable from any object type bound to a puzzle (design doc
            # §6.2), so this is checked before the per-type dispatch below.
            puzzle_id = record["config"].get("puzzleId")
            if puzzle_id is None:
                raise ValueError(f"object {object_id} has no bound puzzle")
            return {"puzzle": self._puzzles.get_puzzle_public(puzzle_id)}
        if record["objectType"] == "escape_door":
            if interaction_type == "attempt_open":
                return self._attempt_open_door(record, requester_id, now_ms, display_name)
        if record["objectType"] == "hidden_item":
            if interaction_type == "pick_up":
                return self._pick_up_item(record, requester_id)
        if record["objectType"] == "bookshelf":
            if interaction_type == "browse_books":
                books = []
                for book in self._bookshelf.list_books(object_id):
                    progress = self._bookshelf.get_progress(object_id, book["bookId"], requester_id)
                    books.append({**book, "progress": progress["progress"] if progress else 0})
                return {"books": books}
            if interaction_type == "resume_reading":
                resume = self._bookshelf.get_resume_book(object_id, requester_id)
                return resume if resume is not None else {"book": None}
        if record["objectType"] == "tv":
            sync_session = self._media.get_sync_session(object_id, now_ms=now_ms)
            if interaction_type == "open_playlist":
                return {"videos": self._media.list_videos(object_id), "syncSession": sync_session}
            if interaction_type == "watch_video":
                videos = self._media.list_videos(object_id)
                default_video = self._pick_default_media_item(videos, "videoId", sync_session)
                return {"video": default_video, "syncSession": sync_session}
        if record["objectType"] == "music_player":
            sync_session = self._media.get_sync_session(object_id, now_ms=now_ms)
            if interaction_type == "view_playlist":
                return {"tracks": self._media.list_tracks(object_id), "syncSession": sync_session}
            if interaction_type == "play_track":
                tracks = self._media.list_tracks(object_id)
                default_track = self._pick_default_media_item(tracks, "trackId", sync_session)
                return {"track": default_track, "syncSession": sync_session}
        if record["objectType"] == "ai_character":
            character = self._story.get_character(object_id, object_id)
            if interaction_type == "talk":
                story_result = self._story.talk(object_id, object_id, user_id=requester_id)
                return {"character": character, **story_result}
            if interaction_type == "start_mission":
                story_result = self._story.restart_story(object_id, object_id, user_id=requester_id)
                return {"character": character, **story_result}
            if interaction_type == "ask_hint":
                # An ai_character optionally "guards" a puzzle (design doc
                # §6.5): if configured, ask_hint dispenses that puzzle's next
                # hint instead of just returning the character with no
                # content, reusing 100% of the existing interaction plumbing.
                guards_puzzle_id = record["config"].get("guardsPuzzleId")
                if guards_puzzle_id is None:
                    return {"character": character}
                hint_result = self._puzzles.request_hint(guards_puzzle_id, requester_id, now_ms)
                return {"character": character, **hint_result}
        return dict(record["config"])

    def _attempt_open_door(
        self, record: dict[str, Any], requester_id: str, now_ms: float, display_name: str | None,
    ) -> dict[str, Any]:
        """Design doc §5.1/§8.3: opens for `requester_id` once the authored
        gate (required item AND all required puzzles) is satisfied. A door
        with no gate configured at all opens unconditionally on first
        attempt. Idempotent once already open for that visitor."""
        object_id = record["objectId"]
        config = record["config"]
        destination_tile = config.get("destinationTile")
        if self._escape.has_opened(requester_id, object_id):
            return {"opened": True, "alreadyOpen": True, "destinationTile": destination_tile}

        required_item_id = config.get("requiredItemId")
        required_puzzle_ids = config.get("requiredPuzzleIds") or []
        has_item = required_item_id is None or self._inventory.has(requester_id, required_item_id)
        puzzles_solved = all(self._puzzles.is_solved(pid, requester_id) for pid in required_puzzle_ids)
        if not (has_item and puzzles_solved):
            return {"opened": False, "alreadyOpen": False}

        self._escape.open_door(requester_id, object_id)
        if destination_tile is None:
            # No destination tile means this door is a win trigger (§5.1,
            # §8.3); multiple win-doors are OR-gated, and mark_won is a no-op
            # unless the visitor's session is currently in_progress.
            self._escape.mark_won(requester_id, display_name or requester_id, now_ms)
        return {"opened": True, "alreadyOpen": False, "destinationTile": destination_tile}

    def _pick_up_item(self, record: dict[str, Any], requester_id: str) -> dict[str, Any]:
        """Design doc §5.2/§7: a visitor cannot pick up an item they haven't
        personally uncovered yet."""
        object_id = record["objectId"]
        if not self._escape.has_revealed(requester_id, object_id):
            raise PermissionError(f"item {object_id} has not been revealed for this user")
        self._inventory.grant(requester_id, object_id)
        return {"granted": True, "itemId": object_id}

    @staticmethod
    def _pick_default_media_item(
        items: list[dict[str, Any]], id_field: str, sync_session: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Prefer the item an active watch/listen-together session is on, so
        opening the object shows what everyone is already watching/listening
        to instead of an arbitrary default that would visually contradict the
        "watching together" status shown alongside it."""
        if sync_session is not None:
            synced_item = next((item for item in items if item[id_field] == sync_session["itemId"]), None)
            if synced_item is not None:
                return synced_item
        return items[0] if items else None

    def set_locked(
        self, object_id: str, locked: bool, requester_id: str | None = None, is_room_host: bool = False
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        record["isLocked"] = locked
        return dict(record)

    def set_z_index(
        self, object_id: str, z_index: int, requester_id: str | None = None, is_room_host: bool = False
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        self._require_unlocked(record)
        record["zIndex"] = z_index
        return dict(record)

    def bring_to_front(
        self, object_id: str, requester_id: str | None = None, is_room_host: bool = False
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        self._require_unlocked(record)
        others = [o["zIndex"] for oid, o in self._objects.items() if oid != object_id]
        record["zIndex"] = (max(others) + 1) if others else 0
        return dict(record)

    def send_to_back(
        self, object_id: str, requester_id: str | None = None, is_room_host: bool = False
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        self._require_edit_permission(record, requester_id, is_room_host)
        self._require_unlocked(record)
        others = [o["zIndex"] for oid, o in self._objects.items() if oid != object_id]
        record["zIndex"] = (min(others) - 1) if others else 0
        return dict(record)

    def delete_object(
        self, object_id: str, requester_id: str | None = None, is_room_host: bool = False
    ) -> bool:
        record = self._objects.get(object_id)
        if record is None:
            return False
        self._require_edit_permission(record, requester_id, is_room_host)
        self._require_unlocked(record)
        del self._objects[object_id]
        if record["objectType"] == "ai_character":
            # Otherwise a deleted character's route would keep being ticked by
            # the game loop, and re-creating an object with a recycled id
            # would inherit the old character's tour and profile.
            self._guide.discard(object_id)
            self._story.remove_character(object_id, object_id)
        if record["objectType"] == "hidden_item":
            # Otherwise a recycled object id would inherit a phantom held
            # item / stale reveal flag from before it was deleted (§5.3).
            self._inventory.revoke_all_for_object(object_id)
            self._escape.clear_revealed_for_object(object_id)
        if record["objectType"] == "escape_door":
            self._escape.clear_opened_for_object(object_id)
        puzzle_id = record["config"].get("puzzleId")
        if puzzle_id is not None and not self._puzzle_id_still_referenced(puzzle_id):
            # No dangling puzzle definition left behind once nothing else
            # (another bound object, or an ai_character's guardsPuzzleId)
            # still references it (§5.3).
            self._puzzles.remove_puzzle(puzzle_id)
        return True

    def _puzzle_id_still_referenced(self, puzzle_id: str) -> bool:
        for other in self._objects.values():
            if other["config"].get("puzzleId") == puzzle_id:
                return True
            if other["objectType"] == "ai_character" and other["config"].get("guardsPuzzleId") == puzzle_id:
                return True
        return False

    # ── Escape room orchestration (design doc §6.1, §8) ──────────────────

    def _require_room_host(self, requester_id: str | None, is_room_host: bool) -> None:
        """Host-only gate for room-wide (non-object-bound) escape-room admin
        actions -- puzzle authoring and escape-session configuration have no
        single owning object for `_require_edit_permission` to check against,
        so access is restricted to the room host, mirroring
        `configure_character_generative_mode`'s existing room-host gate.
        `requester_id is None` means a trusted/internal caller (existing
        tests, server-side migrations) and is always allowed, matching the
        same convention `_can_edit`/`list_objects` already use."""
        if requester_id is not None and not is_room_host:
            raise PermissionError("only the room host can manage this")

    def add_puzzle(
        self,
        puzzle_id: str,
        prompt: str,
        answer: str,
        hints: list[str] | None = None,
        reveal_item_id: str | None = None,
        unlock_door_id: str | None = None,
        match_mode: str = "exact",
        max_attempts: int | None = None,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> dict[str, Any]:
        """Thin orchestrator (design doc §6.1): `PuzzleEngine` has no
        reference to room objects and must not reach into `self._objects`
        to stay independently testable, so `RoomBuilderState` owns the
        atomic, two-sided wiring between a puzzle and the door it unlocks
        instead. `unlock_door_id` is validated *before* creating the puzzle
        so a bad reference never leaves a dangling puzzle definition behind.
        """
        self._require_room_host(requester_id, is_room_host)
        if unlock_door_id is not None:
            self._require_object(unlock_door_id)
        result = self._puzzles.add_puzzle(
            puzzle_id, prompt, answer, hints=hints, reveal_item_id=reveal_item_id,
            unlock_door_id=unlock_door_id, match_mode=match_mode, max_attempts=max_attempts,
        )
        if unlock_door_id is not None:
            door_config = self._objects[unlock_door_id]["config"]
            door_config.setdefault("requiredPuzzleIds", []).append(puzzle_id)
        return result

    def remove_puzzle(
        self, puzzle_id: str, requester_id: str | None = None, is_room_host: bool = False
    ) -> bool:
        self._require_room_host(requester_id, is_room_host)
        return self._puzzles.remove_puzzle(puzzle_id)

    def list_puzzles(self) -> list[dict[str, Any]]:
        return self._puzzles.list_puzzles()

    def attempt_solve_puzzle(
        self, puzzle_id: str, requester_id: str, guess: str, now_ms: float
    ) -> dict[str, Any]:
        result = self._puzzles.attempt_solve(puzzle_id, requester_id, guess, now_ms)
        if result["correct"]:
            # "reveal is driven purely by reveal_item_id" (§6.1) -- solving
            # the puzzle is the reward trigger itself, so this is the one
            # place that calls `reveal_item`, not a separate client round
            # trip. Idempotent to call again on an already-solved re-check.
            reveal_item_id = self._puzzles.get_puzzle_public(puzzle_id)["revealItemId"]
            if reveal_item_id is not None:
                self._escape.reveal_item(requester_id, reveal_item_id)
        return result

    def request_puzzle_hint(self, puzzle_id: str, requester_id: str, now_ms: float) -> dict[str, Any]:
        return self._puzzles.request_hint(puzzle_id, requester_id, now_ms)

    def reset_puzzle_attempts(
        self, puzzle_id: str, user_id: str, requester_id: str | None = None, is_room_host: bool = False
    ) -> None:
        self._require_room_host(requester_id, is_room_host)
        self._puzzles.reset_attempts(puzzle_id, user_id)

    def configure_escape_session(
        self,
        enabled: bool,
        time_limit_ms: float,
        briefing: str | None = None,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> None:
        self._require_room_host(requester_id, is_room_host)
        self._escape.configure(enabled, time_limit_ms, briefing)

    def start_escape_session(self, requester_id: str, now_ms: float) -> dict[str, Any]:
        return self._escape.start(requester_id, now_ms)

    def get_escape_status(self, requester_id: str, now_ms: float) -> dict[str, Any]:
        return self._escape.status(requester_id, now_ms)

    def get_escape_briefing(self) -> str | None:
        return self._escape.get_briefing()

    def reset_escape_session(self, requester_id: str) -> None:
        """Self-serve retry (room:escape:reset, §9): a visitor may only ever
        reset their own session, so no room-host gate is needed here --
        `EscapeSessionEngine.reset` already restricts itself to that one
        user_id's state and rejects an in-progress session with
        `PermissionError` (§8.1)."""
        self._escape.reset(requester_id)

    def escape_leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._escape.leaderboard(limit)

    def expire_escape_sessions(self, now_ms: float) -> list[str]:
        """Thin accessor so `server/main.py`'s game loop (§8.3) can expire
        overdue sessions each tick, mirroring `tick_character_tours`'s
        per-tick engine-driving wrappers, without reaching into `_escape`
        directly."""
        return self._escape.expire_overdue_sessions(now_ms)

    def list_inventory(self, requester_id: str) -> list[str]:
        return self._inventory.list_items(requester_id)

    def has_opened_door(self, object_id: str, requester_id: str) -> bool:
        """Thin accessor so `server/main.py`'s collision code (\u00a75.1) can
        check per-visitor door-open state without reaching into the private
        `_escape` engine directly -- the same discipline every other
        cross-module caller already follows."""
        return self._escape.has_opened(requester_id, object_id)

    def reveal_item(self, requester_id: str, object_id: str) -> None:
        """Thin accessor for a fired `reveal_object` trigger (design doc
        feature_designs/escape_room_feature_design.md \u00a76.3) so
        `server/main.py`'s game loop can mark a hidden_item revealed for the
        triggering visitor without reaching into the private `_escape`
        engine directly. Idempotent like the puzzle-solve reveal path."""
        self._escape.reveal_item(requester_id, object_id)

    def configure_door(
        self,
        object_id: str,
        required_item_id: str | None = None,
        required_puzzle_ids: list[str] | None = None,
        destination_tile: dict[str, int] | None = None,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        if record["objectType"] != "escape_door":
            raise ValueError(f"object {object_id} is not an escape_door")
        self._require_edit_permission(record, requester_id, is_room_host)
        if required_item_id is not None:
            record["config"]["requiredItemId"] = required_item_id
        if required_puzzle_ids is not None:
            record["config"]["requiredPuzzleIds"] = list(required_puzzle_ids)
        if destination_tile is not None:
            record["config"]["destinationTile"] = destination_tile
        return dict(record)

    def configure_item(
        self,
        object_id: str,
        item_kind: str | None = None,
        single_use: bool | None = None,
        requester_id: str | None = None,
        is_room_host: bool = False,
    ) -> dict[str, Any]:
        record = self._require_object(object_id)
        if record["objectType"] != "hidden_item":
            raise ValueError(f"object {object_id} is not a hidden_item")
        self._require_edit_permission(record, requester_id, is_room_host)
        if item_kind is not None:
            record["config"]["itemKind"] = item_kind
        if single_use is not None:
            record["config"]["singleUse"] = single_use
        return dict(record)

    # ── Collision / interaction zone editor ──────────────────────────────

    def create_zone(
        self,
        zone_id: str,
        tile: tuple[int, int],
        zone_type: str,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> dict[str, Any]:
        if zone_type not in _VALID_ZONE_TYPES:
            raise ValueError(f"invalid zone type: {zone_type}")
        bounds = BoundsModel(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)
        record = {
            "zoneId": zone_id,
            "tile": tile,
            "zoneType": zone_type,
            "minX": bounds.min_x,
            "minY": bounds.min_y,
            "maxX": bounds.max_x,
            "maxY": bounds.max_y,
        }
        self._zones[zone_id] = record
        return dict(record)

    def delete_zone(self, zone_id: str) -> bool:
        if zone_id not in self._zones:
            return False
        del self._zones[zone_id]
        return True

    def get_zone(self, zone_id: str) -> dict[str, Any] | None:
        record = self._zones.get(zone_id)
        return dict(record) if record else None

    def list_zones(self) -> list[dict[str, Any]]:
        return [dict(z) for z in self._zones.values()]

    def point_in_zone(self, zone_id: str, x: float, y: float) -> bool:
        zone = self._zones.get(zone_id)
        if zone is None:
            return False
        return zone["minX"] <= x <= zone["maxX"] and zone["minY"] <= y <= zone["maxY"]

    def zones_containing_point(
        self,
        tile: tuple[int, int],
        x: float,
        y: float,
        zone_type: str | None = None,
    ) -> list[dict[str, Any]]:
        hits = []
        for zone in self._zones.values():
            if zone["tile"] != tile:
                continue
            if zone_type is not None and zone["zoneType"] != zone_type:
                continue
            if zone["minX"] <= x <= zone["maxX"] and zone["minY"] <= y <= zone["maxY"]:
                hits.append(dict(zone))
        return hits

    # ── Scripted trigger editor (area-enter events) ──────────────────────

    def create_trigger(
        self,
        trigger_id: str,
        tile: tuple[int, int],
        event_type: str,
        payload: dict[str, Any],
        zone_id: str | None = None,
        repeatable: bool = False,
        cooldown_ms: float = 0.0,
    ) -> dict[str, Any]:
        if zone_id is None or zone_id not in self._zones:
            raise ValueError(f"unknown zone: {zone_id}")
        record = {
            "triggerId": trigger_id,
            "tile": tile,
            "zoneId": zone_id,
            "eventType": event_type,
            "payload": payload,
            "repeatable": repeatable,
            "cooldownMs": cooldown_ms,
        }
        self._triggers[trigger_id] = record
        return dict(record)

    def delete_trigger(self, trigger_id: str) -> bool:
        if trigger_id not in self._triggers:
            return False
        del self._triggers[trigger_id]
        return True

    def list_triggers(self) -> list[dict[str, Any]]:
        return [dict(t) for t in self._triggers.values()]

    def evaluate_area_enter(
        self,
        player_id: str,
        tile: tuple[int, int],
        x: float,
        y: float,
        now_ms: float,
    ) -> list[dict[str, Any]]:
        fired: list[dict[str, Any]] = []
        for trigger in self._triggers.values():
            if trigger["tile"] != tile:
                continue
            key = (player_id, trigger["triggerId"])
            is_inside = self.point_in_zone(trigger["zoneId"], x, y)
            was_inside = self._trigger_inside_state.get(key, False)
            self._trigger_inside_state[key] = is_inside

            if not is_inside or was_inside:
                continue  # only fire on the outside -> inside transition

            if not trigger["repeatable"]:
                if key in self._trigger_fired_ever:
                    continue
                self._trigger_fired_ever.add(key)
            else:
                last_fired = self._trigger_last_fired_ms.get(key)
                if last_fired is not None and (now_ms - last_fired) < trigger["cooldownMs"]:
                    continue
                self._trigger_last_fired_ms[key] = now_ms

            fired.append({
                "triggerId": trigger["triggerId"],
                "eventType": trigger["eventType"],
                "payload": trigger["payload"],
            })
        return fired

    # ── Save draft / publish / rollback ──────────────────────────────────

    def save_draft(
        self,
        snapshot: dict[str, Any],
        created_by: str,
        change_notes: str | None = None,
    ) -> dict[str, Any]:
        version_number = self._next_version
        self._next_version += 1
        record = {
            "versionNumber": version_number,
            "snapshot": snapshot,
            "createdBy": created_by,
            "changeNotes": change_notes,
            "isActive": False,
        }
        self._versions.append(record)
        return dict(record)

    def list_versions(self) -> list[dict[str, Any]]:
        return [dict(v) for v in sorted(self._versions, key=lambda v: v["versionNumber"], reverse=True)]

    def _require_version(self, version_number: int) -> dict[str, Any]:
        for version in self._versions:
            if version["versionNumber"] == version_number:
                return version
        raise ValueError(f"unknown version: {version_number}")

    def publish(self, version_number: int, published_by: str) -> dict[str, Any]:
        target = self._require_version(version_number)
        for version in self._versions:
            version["isActive"] = False
        target["isActive"] = True
        target["publishedBy"] = published_by
        self._active_version = version_number
        return dict(target)

    def get_active_published_version(self) -> dict[str, Any] | None:
        if self._active_version is None:
            return None
        return dict(self._require_version(self._active_version))

    def rollback(self, version_number: int) -> dict[str, Any]:
        target = self._require_version(version_number)
        return dict(target["snapshot"])
