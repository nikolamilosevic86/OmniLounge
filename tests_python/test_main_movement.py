import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar


class FakeSio:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data=None, room=None, skip_sid=None):
        self.emitted.append((event, data, room))

    async def enter_room(self, sid, room):
        return None

    async def leave_room(self, sid, room):
        return None


@pytest.fixture(autouse=True)
def isolate_registry(monkeypatch):
    """Give each test a clean rooms registry and a fake sio so no real
    network/db access happens, and tests don't leak player state."""
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)

    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    return fresh_rooms, fake_sio


class TestPlayerMoveHandlesMalformedInput:
    """A raw/malicious socket client can send any JSON payload for
    player:move; the handler must not raise on missing or non-numeric
    x/y instead of trusting the client to always send well-formed data."""

    async def test_player_move_with_valid_coordinates_still_works(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_move("p1", {"x": 100, "y": 150})

        moving_events = [e for e in fake_sio.emitted if e[0] == "player:moving"]
        assert moving_events
        assert moving_events[-1][1]["targetPosition"]["x"] == 100

    async def test_player_move_with_missing_x_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_move("p1", {"y": 150})

    async def test_player_move_with_missing_data_keys_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_move("p1", {})

    async def test_player_move_with_non_numeric_coordinates_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_move("p1", {"x": "not-a-number", "y": "also-not"})


class TestPlayerActionHandlesMalformedTarget:
    """Both the teleport and walk-to-target branches of player:action
    forward `target` into clamp_position(); malformed target dicts must
    not crash the handler."""

    async def test_player_action_teleport_with_malformed_target_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_action("p1", {"teleport": True, "target": {"foo": "bar"}})

    async def test_player_action_walk_to_target_with_malformed_target_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_action("p1", {"target": {"x": "nope"}})

    async def test_player_action_teleport_with_valid_target_still_works(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_action("p1", {"teleport": True, "target": {"x": 200, "y": 250}})

        room = rooms.get_room("lobby")
        player = room.get_player("p1")
        assert player["position"]["x"] == 200
