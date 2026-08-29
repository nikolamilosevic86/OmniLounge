"""TDD coverage for RoomsRegistry.set_room_style (design doc
feature_designs/build_mode_ui_redesign_feature_design.md §11): lets a room's
host change the room's ambient style after creation, validated against the
existing ROOM_STYLE_IDS and gated behind room-host permission, mirroring the
existing `_require_edit_permission`-equivalent pattern used everywhere else
in RoomBuilderState.
"""
import pytest

from server.game.room_styles import DEFAULT_ROOM_STYLE, ROOM_STYLE_IDS
from server.game.rooms_registry import RoomsRegistry


class TestSetRoomStyle:
    def test_room_host_can_change_the_style(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="host-1", name="History Lab")
        chosen = next(s for s in ROOM_STYLE_IDS if s != DEFAULT_ROOM_STYLE)

        result = registry.set_room_style(room["id"], chosen, requester_id="host-1", is_room_host=True)

        assert result == chosen
        assert registry.get_room_style(room["id"]) == chosen

    def test_non_host_cannot_change_the_style(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="host-1", name="History Lab")
        chosen = next(s for s in ROOM_STYLE_IDS if s != DEFAULT_ROOM_STYLE)

        with pytest.raises(PermissionError):
            registry.set_room_style(room["id"], chosen, requester_id="guest-1", is_room_host=False)

        assert registry.get_room_style(room["id"]) == DEFAULT_ROOM_STYLE

    def test_invalid_style_id_is_rejected(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="host-1", name="History Lab")

        with pytest.raises(ValueError):
            registry.set_room_style(room["id"], "haunted-mansion", requester_id="host-1", is_room_host=True)

        assert registry.get_room_style(room["id"]) == DEFAULT_ROOM_STYLE

    def test_unknown_room_id_raises_key_error(self):
        registry = RoomsRegistry()

        with pytest.raises(KeyError):
            registry.set_room_style("unknown-room", DEFAULT_ROOM_STYLE, requester_id="host-1", is_room_host=True)
