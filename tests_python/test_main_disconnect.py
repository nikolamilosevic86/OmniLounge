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


class TestDisconnectHandler:
    async def test_disconnect_removes_player_from_their_room(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.disconnect("p1")

        assert rooms.get_player_room_id("p1") is None
        assert rooms.get_room("lobby").get_player("p1") is None

    async def test_disconnect_notifies_remaining_players_in_the_room(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar1 = create_default_avatar("Alice")
        avatar2 = create_default_avatar("Bob")
        rooms.join_room("p1", avatar1, "lobby")
        rooms.join_room("p2", avatar2, "lobby")

        await main_module.disconnect("p1")

        left_events = [e for e in fake_sio.emitted if e[0] == "player:left"]
        assert left_events
        assert left_events[-1][1]["id"] == "p1"
        assert left_events[-1][2] == "room:lobby"

        state_events = [e for e in fake_sio.emitted if e[0] == "room:state" and e[2] == "room:lobby"]
        assert state_events
        remaining_ids = {p["id"] for p in state_events[-1][1]["players"]}
        assert remaining_ids == {"p2"}

    async def test_disconnect_broadcasts_room_list_changed(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.disconnect("p1")

        assert any(e[0] == "room:list:changed" for e in fake_sio.emitted)

    async def test_disconnect_for_player_not_in_any_room_is_a_safe_noop(self, isolate_registry):
        rooms, fake_sio = isolate_registry

        await main_module.disconnect("ghost-sid")

        assert not [e for e in fake_sio.emitted if e[0] in {"player:left", "room:state", "room:list:changed"}]

    async def test_disconnect_only_notifies_the_players_own_room_not_others(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host1", name="Other Room")
        avatar1 = create_default_avatar("Alice")
        avatar2 = create_default_avatar("Bob")
        rooms.join_room("p1", avatar1, "lobby")
        rooms.join_room("p2", avatar2, room["id"])

        await main_module.disconnect("p2")

        lobby_state_events = [e for e in fake_sio.emitted if e[0] == "room:state" and e[2] == "room:lobby"]
        assert not lobby_state_events, "disconnecting from a different room must not touch the lobby"
        other_room_events = [e for e in fake_sio.emitted if e[0] == "player:left" and e[2] == f"room:{room['id']}"]
        assert other_room_events
