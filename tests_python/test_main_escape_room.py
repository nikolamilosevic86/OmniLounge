import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar
from server.game.puzzle_templates import PUZZLE_TEMPLATES, get_template


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

    async def test_start_before_escape_mode_is_configured_emits_error_not_a_crash(self, isolate_registry):
        # PermissionError from EscapeSessionEngine.start()'s _require_enabled()
        # guard must be caught here like every other handler that calls into
        # an engine method that can raise, instead of propagating uncaught.
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        result = await main_module.room_escape_start("p1", {})

        assert result is None
        assert _errors(fake_sio)

    async def test_status_includes_briefing_text(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")
        await main_module.room_escape_configure(
            "host-1", {"enabled": True, "timeLimitMs": 60_000, "briefing": "Find the key."},
        )

        status = await main_module.room_escape_status("host-1", {})

        assert status["briefing"] == "Find the key."

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

    async def test_configure_with_team_mode_flag_enables_team_mode(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")

        result = await main_module.room_escape_configure(
            "host-1", {"enabled": True, "timeLimitMs": 60_000, "teamMode": True},
        )

        assert result is True
        builder = rooms.get_builder(room_id)
        assert builder.is_escape_team_mode() is True

    async def test_configure_without_team_mode_flag_defaults_to_disabled(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")

        await main_module.room_escape_configure("host-1", {"enabled": True, "timeLimitMs": 60_000})

        builder = rooms.get_builder(room_id)
        assert builder.is_escape_team_mode() is False


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


# ─── Phase 3: puzzle templates, analytics, global leaderboard (§14) ────────

class TestPuzzleTemplateHandlers:
    async def test_templates_list_returns_the_catalog(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        result = await main_module.room_puzzle_templates("p1", {})

        assert {t["templateId"] for t in result} == set(PUZZLE_TEMPLATES)

    async def test_templates_list_without_a_room_errors(self, isolate_registry):
        rooms, fake_sio = isolate_registry

        result = await main_module.room_puzzle_templates("ghost", {})

        assert result is None
        assert _errors(fake_sio)

    async def test_add_from_template_applies_its_match_mode_preset(self, isolate_registry):
        # Regression guard: the handler used to default matchMode to
        # "exact", which silently clobbered a template's own preset.
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        await _join(rooms, room["id"], "host-1", "Host")

        added = await main_module.room_puzzle_add(
            "host-1",
            {"puzzleId": "lock-1", "templateId": "number_lock", "answer": "1234"},
        )

        assert added["matchMode"] == "numeric"

    async def test_add_from_template_fills_in_the_prompt(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        await _join(rooms, room["id"], "host-1", "Host")

        added = await main_module.room_puzzle_add(
            "host-1", {"puzzleId": "r-1", "templateId": "riddle", "answer": "a keyboard"},
        )

        assert added["prompt"] == get_template("riddle")["promptTemplate"]

    async def test_explicit_match_mode_still_wins_over_the_template(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        await _join(rooms, room["id"], "host-1", "Host")

        added = await main_module.room_puzzle_add(
            "host-1",
            {"puzzleId": "lock-1", "templateId": "number_lock", "answer": "1234",
             "matchMode": "contains"},
        )

        assert added["matchMode"] == "contains"

    async def test_add_without_a_template_still_defaults_to_exact(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        await _join(rooms, room["id"], "host-1", "Host")

        added = await main_module.room_puzzle_add(
            "host-1", {"puzzleId": "r-1", "prompt": "2+2?", "answer": "4"},
        )

        assert added["matchMode"] == "exact"

    async def test_add_without_a_template_still_requires_a_prompt(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        await _join(rooms, room["id"], "host-1", "Host")

        result = await main_module.room_puzzle_add(
            "host-1", {"puzzleId": "r-1", "answer": "4"},
        )

        assert result is None
        assert _errors(fake_sio)

    async def test_unknown_template_emits_an_error(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        await _join(rooms, room["id"], "host-1", "Host")

        result = await main_module.room_puzzle_add(
            "host-1", {"puzzleId": "r-1", "templateId": "sudoku", "answer": "x"},
        )

        assert result is None
        assert _errors(fake_sio)


class TestPuzzleAnalyticsHandler:
    async def _host_room_with_puzzle(self, rooms):
        room = rooms.create_room(host_id="host-1", name="Test Room")
        await _join(rooms, room["id"], "host-1", "Host")
        builder = rooms.get_builder(room["id"])
        builder.add_puzzle("riddle-1", "2+2?", "4", hints=["It's even."])
        return room["id"], builder

    async def test_room_host_sees_analytics_for_every_puzzle(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        _room_id, builder = await self._host_room_with_puzzle(rooms)
        builder.attempt_solve_puzzle("riddle-1", requester_id="p2", guess="5", now_ms=1)

        result = await main_module.room_puzzle_analytics("host-1", {})

        assert result[0]["puzzleId"] == "riddle-1"
        assert result[0]["wrongAttempts"] == 1

    async def test_single_puzzle_analytics_by_id(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._host_room_with_puzzle(rooms)

        result = await main_module.room_puzzle_analytics("host-1", {"puzzleId": "riddle-1"})

        assert result["puzzleId"] == "riddle-1"

    async def test_non_host_participant_is_rejected(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        rooms.get_builder("lobby").add_puzzle("riddle-1", "2+2?", "4")

        result = await main_module.room_puzzle_analytics("p1", {})

        assert result is None
        assert _errors(fake_sio)

    async def test_unknown_puzzle_id_emits_an_error(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._host_room_with_puzzle(rooms)

        result = await main_module.room_puzzle_analytics("host-1", {"puzzleId": "ghost"})

        assert result is None
        assert _errors(fake_sio)

    async def test_without_a_room_errors(self, isolate_registry):
        rooms, fake_sio = isolate_registry

        result = await main_module.room_puzzle_analytics("ghost", {})

        assert result is None
        assert _errors(fake_sio)

    async def test_analytics_never_expose_the_answer(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        _room_id, builder = await self._host_room_with_puzzle(rooms)
        builder.attempt_solve_puzzle("riddle-1", requester_id="p2", guess="4", now_ms=1)

        result = await main_module.room_puzzle_analytics("host-1", {})

        assert "answer" not in result[0]
        assert result[0]["commonWrongGuesses"] == []


class TestGlobalEscapeLeaderboardHandler:
    async def _room_with_win(self, rooms, name, player, elapsed_ms, host_id):
        room = rooms.create_room(host_id=host_id, name=name)
        builder = rooms.get_builder(room["id"])
        builder.configure_escape_session(True, 600_000.0)
        builder.start_escape_session(player, now_ms=0.0)
        builder._escape.mark_won(player, player, now_ms=elapsed_ms)
        return room["id"]

    async def test_starts_empty(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        assert await main_module.room_escape_leaderboard_global("p1", {}) == []

    async def test_aggregates_across_rooms_sorted_by_time(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._room_with_win(rooms, "Alpha", "Slow", 9_000.0, "h1")
        await self._room_with_win(rooms, "Beta", "Fast", 1_000.0, "h2")
        await _join(rooms)

        board = await main_module.room_escape_leaderboard_global("p1", {})

        assert [e["displayName"] for e in board] == ["Fast", "Slow"]
        assert board[0]["roomName"] == "Beta"

    async def test_respects_the_limit(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._room_with_win(rooms, "Alpha", "Slow", 9_000.0, "h1")
        await self._room_with_win(rooms, "Beta", "Fast", 1_000.0, "h2")
        await _join(rooms)

        board = await main_module.room_escape_leaderboard_global("p1", {"limit": 1})

        assert [e["displayName"] for e in board] == ["Fast"]

    async def test_bad_limit_falls_back_to_the_default(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._room_with_win(rooms, "Alpha", "Alice", 5_000.0, "h1")
        await _join(rooms)

        board = await main_module.room_escape_leaderboard_global("p1", {"limit": "lots"})

        assert len(board) == 1

    async def test_without_a_room_errors(self, isolate_registry):
        # Consistent with every other room-scoped handler: you have to be
        # in the world to read the world's board.
        rooms, fake_sio = isolate_registry

        result = await main_module.room_escape_leaderboard_global("ghost", {})

        assert result is None
        assert _errors(fake_sio)


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


class TestDoorDestinationTileWarp:
    """design doc §8.3: opening an escape_door with a destinationTile
    transitions the visitor to that tile via the same mechanism as a normal
    edge crossing, instead of marking a win."""

    async def test_opening_a_door_with_destination_tile_moves_the_player(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        rooms.add_neighbor_tile("lobby", (0, 0), "right")
        builder = rooms.get_builder("lobby")
        builder.create_object("door-1", "escape_door", (0, 0), x=10, y=10, width=20, height=20)
        builder.get_object("door-1")["config"]["destinationTile"] = {"x": 1, "y": 0}

        await main_module.room_object_interact(
            "p1", {"objectId": "door-1", "interactionType": "attempt_open"},
        )

        assert rooms.get_player_tile("p1") == (1, 0)
        room = rooms.get_room("lobby")
        assert room.get_player("p1")["tile"] == {"x": 1, "y": 0}

    async def test_opening_a_door_with_destination_tile_broadcasts_room_state(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        rooms.add_neighbor_tile("lobby", (0, 0), "right")
        builder = rooms.get_builder("lobby")
        builder.create_object("door-1", "escape_door", (0, 0), x=10, y=10, width=20, height=20)
        builder.get_object("door-1")["config"]["destinationTile"] = {"x": 1, "y": 0}

        await main_module.room_object_interact(
            "p1", {"objectId": "door-1", "interactionType": "attempt_open"},
        )

        state_events = [e for e in fake_sio.emitted if e[0] == "room:state"]
        assert state_events

    async def test_opening_a_door_whose_destination_tile_does_not_exist_does_not_error(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.create_object("door-1", "escape_door", (0, 0), x=10, y=10, width=20, height=20)
        builder.get_object("door-1")["config"]["destinationTile"] = {"x": 9, "y": 9}

        await main_module.room_object_interact(
            "p1", {"objectId": "door-1", "interactionType": "attempt_open"},
        )

        assert rooms.get_player_tile("p1") == (0, 0)
        assert not _errors(fake_sio)

    async def test_reopening_an_already_open_destination_door_warps_again(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        rooms.add_neighbor_tile("lobby", (0, 0), "right")
        builder = rooms.get_builder("lobby")
        builder.create_object("door-1", "escape_door", (0, 0), x=10, y=10, width=20, height=20)
        builder.get_object("door-1")["config"]["destinationTile"] = {"x": 1, "y": 0}
        await main_module.room_object_interact(
            "p1", {"objectId": "door-1", "interactionType": "attempt_open"},
        )
        rooms.player_tile["p1"] = (0, 0)

        await main_module.room_object_interact(
            "p1", {"objectId": "door-1", "interactionType": "attempt_open"},
        )

        assert rooms.get_player_tile("p1") == (1, 0)

    async def test_door_with_no_destination_tile_does_not_warp(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)
        builder = rooms.get_builder("lobby")
        builder.create_object("door-1", "escape_door", (0, 0), x=10, y=10, width=20, height=20)

        await main_module.room_object_interact(
            "p1", {"objectId": "door-1", "interactionType": "attempt_open"},
        )

        assert rooms.get_player_tile("p1") == (0, 0)


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

    async def test_tick_in_team_mode_broadcasts_to_the_whole_room_not_a_sentinel_sid(self, isolate_registry):
        # `expire_escape_sessions` returns `RoomBuilderState.ESCAPE_TEAM_KEY`
        # in team mode (an internal sentinel, never a real socket sid) --
        # emitting `room=that_key` would silently reach nobody, so the tick
        # must broadcast to the room channel instead whenever team mode is on.
        rooms, fake_sio = isolate_registry
        await _join(rooms, player_id="p1", name="Alice")
        await _join(rooms, player_id="p2", name="Bob")
        builder = rooms.get_builder("lobby")
        builder.configure_escape_session(True, 10, team_mode=True, requester_id=None)
        builder.start_escape_session("p1", now_ms=0)

        await main_module.tick_escape_sessions("lobby", now_ms=1000)

        expired_events = [e for e in fake_sio.emitted if e[0] == "room:escape:expired"]
        assert len(expired_events) == 1
        assert expired_events[-1][2] == main_module.room_channel("lobby")


# ─── Escape room: hidden_item visibility must hold over the wire (§5.2/§12) ─
#
# `RoomBuilderState.list_objects`/`list_objects_for_tiles` already filter
# unrevealed hidden_items by requester_id (see TestHiddenItemVisibility in
# test_room_builder.py), but that filtering is only real if the socket layer
# actually threads each recipient's own id through. These tests exercise the
# `room:builder:state` broadcast produced by `server/main.py` itself, not the
# engine directly, to guard against exactly that gap.

class TestHiddenItemVisibilityOverTheWire:
    async def test_broadcast_omits_unrevealed_hidden_item_from_a_normal_visitor(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")
        await _join(rooms, room_id, "p1", "Alice")
        builder = rooms.get_builder(room_id)
        builder.create_object("key-1", "hidden_item", (0, 0), x=5, y=5, width=10, height=10)

        # Any builder-mutating handler triggers `broadcast_builder_state`;
        # escape-session configure is a convenient one already covered above.
        await main_module.room_escape_configure(
            "host-1", {"enabled": True, "timeLimitMs": 60_000}, )

        p1_events = [e for e in fake_sio.emitted if e[0] == "room:builder:state" and e[2] == "p1"]
        assert p1_events, "expected a builder-state broadcast targeted at p1"
        object_ids = {o["objectId"] for o in p1_events[-1][1]["objects"]}
        assert "key-1" not in object_ids

    async def test_broadcast_still_includes_unrevealed_hidden_item_for_the_room_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")
        await _join(rooms, room_id, "p1", "Alice")
        builder = rooms.get_builder(room_id)
        builder.create_object("key-1", "hidden_item", (0, 0), x=5, y=5, width=10, height=10)

        await main_module.room_escape_configure(
            "host-1", {"enabled": True, "timeLimitMs": 60_000}, )

        host_events = [e for e in fake_sio.emitted if e[0] == "room:builder:state" and e[2] == "host-1"]
        assert host_events, "expected a builder-state broadcast targeted at the host"
        object_ids = {o["objectId"] for o in host_events[-1][1]["objects"]}
        assert "key-1" in object_ids

    async def test_broadcast_includes_hidden_item_only_for_the_visitor_who_revealed_it(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        await _join(rooms, room_id, "host-1", "Host")
        await _join(rooms, room_id, "p1", "Alice")
        await _join(rooms, room_id, "p2", "Bob")
        builder = rooms.get_builder(room_id)
        builder.create_object("key-1", "hidden_item", (0, 0), x=5, y=5, width=10, height=10)
        builder._escape.reveal_item("p1", "key-1")

        await main_module.room_escape_configure(
            "host-1", {"enabled": True, "timeLimitMs": 60_000}, )

        p1_events = [e for e in fake_sio.emitted if e[0] == "room:builder:state" and e[2] == "p1"]
        p2_events = [e for e in fake_sio.emitted if e[0] == "room:builder:state" and e[2] == "p2"]
        assert "key-1" in {o["objectId"] for o in p1_events[-1][1]["objects"]}
        assert "key-1" not in {o["objectId"] for o in p2_events[-1][1]["objects"]}


# ─── Trigger-revealed puzzles: reveal_object event type (§6.3) ─────────────

class TestHandleFiredTrigger:
    """`server/main.py: handle_fired_trigger` is what the game loop calls
    for each trigger `apply_player_movement` reports as fired (§6.3).
    Exercised directly since the game loop itself is an infinite loop."""

    async def test_reveal_object_marks_the_item_revealed_for_that_visitor_only(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms, player_id="p1", name="Alice")
        await _join(rooms, player_id="p2", name="Bob")
        builder = rooms.get_builder("lobby")
        builder.create_object("key-1", "hidden_item", (0, 0), x=5, y=5, width=10, height=10)

        await main_module.handle_fired_trigger("lobby", {
            "playerId": "p1", "triggerId": "t1", "eventType": "reveal_object",
            "payload": {"objectId": "key-1"},
        })

        p1_objects = builder.list_objects(requester_id="p1")
        p2_objects = builder.list_objects(requester_id="p2")
        assert any(o["objectId"] == "key-1" for o in p1_objects)
        assert all(o["objectId"] != "key-1" for o in p2_objects)

    async def test_reveal_object_pushes_a_personalized_builder_state_to_that_visitor(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms, player_id="p1", name="Alice")
        builder = rooms.get_builder("lobby")
        builder.create_object("key-1", "hidden_item", (0, 0), x=5, y=5, width=10, height=10)

        await main_module.handle_fired_trigger("lobby", {
            "playerId": "p1", "triggerId": "t1", "eventType": "reveal_object",
            "payload": {"objectId": "key-1"},
        })

        state_events = [e for e in fake_sio.emitted if e[0] == "room:builder:state" and e[2] == "p1"]
        assert state_events
        assert any(o["objectId"] == "key-1" for o in state_events[-1][1]["objects"])

    async def test_every_fired_trigger_is_echoed_to_that_visitor_generically(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms, player_id="p1", name="Alice")

        await main_module.handle_fired_trigger("lobby", {
            "playerId": "p1", "triggerId": "t1", "eventType": "dialogue",
            "payload": {"nodeId": "intro-1"},
        })

        fired_events = [e for e in fake_sio.emitted if e[0] == "room:trigger:fired" and e[2] == "p1"]
        assert fired_events
        assert fired_events[-1][1]["eventType"] == "dialogue"
        assert fired_events[-1][1]["payload"] == {"nodeId": "intro-1"}

    async def test_reveal_object_with_missing_object_id_does_not_error(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms, player_id="p1", name="Alice")

        await main_module.handle_fired_trigger("lobby", {
            "playerId": "p1", "triggerId": "t1", "eventType": "reveal_object", "payload": {},
        })

        state_events = [e for e in fake_sio.emitted if e[0] == "room:builder:state" and e[2] == "p1"]
        assert not state_events  # no valid objectId -> no reveal, no extra broadcast
