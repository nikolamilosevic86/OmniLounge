"""TDD coverage for the `room:style:set` socket handler and the
`roomStyle` field on `builder_state_payload`/`broadcast_builder_state`
(design doc feature_designs/build_mode_ui_redesign_feature_design.md §11,
§14, §17 Decision D1).

Decision D1 folds the room style into the existing `room:builder:state`
broadcast instead of inventing a dedicated event, so these tests assert on
that payload rather than a new event name.
"""
import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar
from server.game.room_styles import DEFAULT_ROOM_STYLE, ROOM_STYLE_IDS


class FakeSio:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data=None, room=None, skip_sid=None):
        self.emitted.append((event, data, room))


@pytest.fixture(autouse=True)
def isolate_registry(monkeypatch):
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)

    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    return fresh_rooms, fake_sio


async def _join(rooms, player_id, room_id):
    avatar = create_default_avatar("Alice")
    rooms.join_room(player_id, avatar, room_id)


class TestBuilderStatePayloadIncludesRoomStyle:
    def test_payload_includes_the_rooms_current_style(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        chosen = next(s for s in ROOM_STYLE_IDS if s != DEFAULT_ROOM_STYLE)
        room = rooms.create_room(host_id="host-1", name="History Lab", room_style=chosen)

        payload = main_module.builder_state_payload(room["id"])

        assert payload["roomStyle"] == chosen

    def test_payload_defaults_for_unknown_room(self, isolate_registry):
        payload = main_module.builder_state_payload("unknown-room")
        assert payload["roomStyle"] == DEFAULT_ROOM_STYLE


class TestRoomStyleSetHandler:
    async def test_host_can_change_style_and_broadcast_carries_new_style(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="History Lab")
        room_id = room["id"]
        await _join(rooms, "host-1", room_id)
        chosen = next(s for s in ROOM_STYLE_IDS if s != DEFAULT_ROOM_STYLE)
        fake_sio.emitted.clear()

        await main_module.room_style_set("host-1", {"styleId": chosen})

        assert rooms.get_room_style(room_id) == chosen
        broadcasts = [e for e in fake_sio.emitted if e[0] == "room:builder:state"]
        assert broadcasts, "expected a room:builder:state broadcast"
        assert broadcasts[-1][1]["roomStyle"] == chosen

    async def test_non_host_rejected_with_error_event(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="History Lab")
        room_id = room["id"]
        await _join(rooms, "guest-1", room_id)
        chosen = next(s for s in ROOM_STYLE_IDS if s != DEFAULT_ROOM_STYLE)
        fake_sio.emitted.clear()

        await main_module.room_style_set("guest-1", {"styleId": chosen})

        assert rooms.get_room_style(room_id) == DEFAULT_ROOM_STYLE
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

    async def test_invalid_style_id_rejected_with_error_event(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="History Lab")
        room_id = room["id"]
        await _join(rooms, "host-1", room_id)
        fake_sio.emitted.clear()

        await main_module.room_style_set("host-1", {"styleId": "haunted-mansion"})

        assert rooms.get_room_style(room_id) == DEFAULT_ROOM_STYLE
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

    async def test_no_room_joined_emits_error(self, isolate_registry):
        _rooms, fake_sio = isolate_registry

        await main_module.room_style_set("stranger", {"styleId": DEFAULT_ROOM_STYLE})

        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors
