import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar


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


async def _join(rooms, room_id="lobby", player_id="p1", name="Alice"):
    avatar = create_default_avatar(name)
    rooms.join_room(player_id, avatar, room_id)


def _errors(fake_sio):
    return [e for e in fake_sio.emitted if e[0] == "error"]


class TestEscapeSessionHandlers:
    async def test_configure_by_non_host_participant_is_rejected(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        await main_module.room_escape_configure("p1", {"enabled": True, "timeLimitMs": 60_000})

        assert _errors(fake_sio)
        builder = rooms.get_builder("lobby")
        assert builder.get_escape_status("p1", now_ms=0)["state"] == "not_started"

    async def test_configure_by_room_host_succeeds(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")

        result = await main_module.room_escape_configure(
            "host-1", {"enabled": True, "timeLimitMs": 60_000, "briefing": "Find the key."},
        )

        assert result is True
        builder_events = [e for e in fake_sio.emitted if e[0] == "room:builder:state"]
        assert builder_events

    async def test_start_then_status_reports_in_progress(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")
        await main_module.room_escape_configure(
            "host-1", {"enabled": True, "timeLimitMs": 60_000}, )

        await main_module.room_escape_start("host-1", {})
        status = await main_module.room_escape_status("host-1", {})

        assert status["state"] == "in_progress"

    async def test_reset_while_in_progress_is_rejected(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")
        await main_module.room_escape_configure("host-1", {"enabled": True, "timeLimitMs": 60_000})
        await main_module.room_escape_start("host-1", {})

        await main_module.room_escape_reset("host-1", {})

        assert _errors(fake_sio)

    async def test_leaderboard_list_starts_empty(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        result = await main_module.room_escape_leaderboard_list("p1", {})

        assert result == []


class TestPuzzleHandlers:
    async def test_add_by_non_host_participant_is_rejected(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        await main_module.room_puzzle_add(
            "p1", {"puzzleId": "riddle-1", "prompt": "2+2?", "answer": "4"},
        )

        assert _errors(fake_sio)

    async def test_add_by_room_host_then_list_and_remove(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")

        added = await main_module.room_puzzle_add(
            "host-1", {"puzzleId": "riddle-1", "prompt": "2+2?", "answer": "4"},
        )
        assert added["puzzleId"] == "riddle-1"

        listed = await main_module.room_puzzle_list("host-1", {})
        assert len(listed) == 1

        removed = await main_module.room_puzzle_remove("host-1", {"puzzleId": "riddle-1"})
        assert removed is True
        assert await main_module.room_puzzle_list("host-1", {}) == []

    async def test_attempt_returns_correct_and_hint_returns_next_hint(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.add_puzzle("riddle-1", "2+2?", "4", hints=["It's even."])

        result = await main_module.room_puzzle_attempt(
            "p1", {"puzzleId": "riddle-1", "guess": "wrong"},
        )
        assert result["correct"] is False

        hint = await main_module.room_puzzle_hint("p1", {"puzzleId": "riddle-1"})
        assert hint["hint"] == "It's even."

    async def test_reset_by_non_host_participant_is_rejected(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.add_puzzle("riddle-1", "2+2?", "4", max_attempts=1)

        await main_module.room_puzzle_reset("p1", {"puzzleId": "riddle-1", "userId": "p1"})

        assert _errors(fake_sio)

    async def test_reset_by_room_host_clears_lockout(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")
        builder = rooms.get_builder(room_id)
        builder.add_puzzle("riddle-1", "2+2?", "4", max_attempts=1)
        builder.attempt_solve_puzzle("riddle-1", requester_id="p1", guess="wrong", now_ms=1)

        await main_module.room_puzzle_reset("host-1", {"puzzleId": "riddle-1", "userId": "p1"})

        result = builder.attempt_solve_puzzle("riddle-1", requester_id="p1", guess="4", now_ms=2)
        assert result["correct"] is True


class TestDoorItemConfigureAndInventory:
    async def test_door_configure_requires_edit_permission(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms, "lobby", "p1", "Alice")
        await _join(rooms, "lobby", "p2", "Bob")
        builder = rooms.get_builder("lobby")
        builder.create_object("door-1", "escape_door", (0, 0), x=10, y=10, width=20, height=20, created_by="p1")

        await main_module.room_door_configure("p2", {"objectId": "door-1", "requiredItemId": "key-1"})

        assert _errors(fake_sio)

    async def test_door_configure_by_owner_succeeds(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.create_object("door-1", "escape_door", (0, 0), x=10, y=10, width=20, height=20, created_by="p1")

        result = await main_module.room_door_configure(
            "p1", {"objectId": "door-1", "requiredItemId": "key-1", "destinationTile": {"x": 1, "y": 0}},
        )

        assert result["config"]["requiredItemId"] == "key-1"

    async def test_item_configure_by_owner_succeeds(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.create_object("key-1", "hidden_item", (0, 0), x=5, y=5, width=10, height=10, created_by="p1")

        result = await main_module.room_item_configure(
            "p1", {"objectId": "key-1", "itemKind": "key", "singleUse": False},
        )

        assert result["config"]["itemKind"] == "key"
        assert result["config"]["singleUse"] is False

    async def test_inventory_list_returns_held_items(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.create_object("key-1", "hidden_item", (0, 0), x=5, y=5, width=10, height=10)
        builder._escape.reveal_item("p1", "key-1")
        builder.interact_with_object("key-1", "pick_up", requester_id="p1", now_ms=0)

        result = await main_module.room_inventory_list("p1", {})

        assert result == ["key-1"]


class TestObjectInteractEmitsWinEvent:
    async def test_opening_a_win_door_emits_room_escape_won(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.configure_escape_session(True, 60_000, requester_id=None)
        builder.create_object("door-1", "escape_door", (0, 0), x=10, y=10, width=20, height=20)
        builder.start_escape_session("p1", now_ms=0)

        result = await main_module.room_object_interact(
            "p1", {"objectId": "door-1", "interactionType": "attempt_open"},
        )

        assert result["payload"]["opened"] is True
        won_events = [e for e in fake_sio.emitted if e[0] == "room:escape:won"]
        assert won_events
        assert any(e[1].get("displayName") == "Alice" for e in won_events)

    async def test_opening_a_non_win_door_does_not_emit_won(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.configure_escape_session(True, 60_000, requester_id=None)
        builder.create_object(
            "door-1", "escape_door", (0, 0), x=10, y=10, width=20, height=20,
        )
        builder.get_object("door-1")["config"]["destinationTile"] = {"x": 1, "y": 0}
        builder.start_escape_session("p1", now_ms=0)

        await main_module.room_object_interact(
            "p1", {"objectId": "door-1", "interactionType": "attempt_open"},
        )

        won_events = [e for e in fake_sio.emitted if e[0] == "room:escape:won"]
        assert not won_events


class TestTickEscapeSessions:
    async def test_tick_emits_expired_event_to_overdue_visitor(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.configure_escape_session(True, 10, requester_id=None)
        builder.start_escape_session("p1", now_ms=0)

        await main_module.tick_escape_sessions("lobby", now_ms=1000)

        expired_events = [e for e in fake_sio.emitted if e[0] == "room:escape:expired"]
        assert expired_events and expired_events[-1][2] == "p1"
