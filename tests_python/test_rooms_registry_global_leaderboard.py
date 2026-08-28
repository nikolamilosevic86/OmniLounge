"""Phase 3: cross-room global escape leaderboard (design doc
feature_designs/escape_room_feature_design.md §14 Phase 3, resolving
§16 Q4 in favour of a cross-room board).

`RoomsRegistry` is the only object that can see every room at once, so it
owns the aggregation -- each `RoomBuilderState`/`EscapeSessionEngine`
keeps knowing only about its own room, exactly as before.
"""

from server.game.rooms_registry import RoomsRegistry


def _room_with_win(registry, name, display_name, elapsed_ms, host_id="h1"):
    """Drive a real win through the engine (rather than poking the
    leaderboard list) so these tests break if the win path ever changes."""
    room = registry.create_room(host_id=host_id, name=name)
    builder = registry.get_builder(room["id"])
    builder.configure_escape_session(True, 600_000.0)
    builder.start_escape_session(display_name, now_ms=0.0)
    builder._escape.mark_won(display_name, display_name, now_ms=elapsed_ms)
    return room["id"]


class TestGlobalEscapeLeaderboard:
    def test_empty_when_no_room_has_any_escape_wins(self):
        registry = RoomsRegistry()
        assert registry.global_escape_leaderboard() == []

    def test_aggregates_wins_across_multiple_rooms(self):
        registry = RoomsRegistry()
        _room_with_win(registry, "Alpha", "Alice", 5_000.0)
        _room_with_win(registry, "Beta", "Bob", 3_000.0)

        board = registry.global_escape_leaderboard()

        assert [entry["displayName"] for entry in board] == ["Bob", "Alice"]

    def test_sorted_by_fastest_elapsed_time_across_rooms(self):
        registry = RoomsRegistry()
        _room_with_win(registry, "Alpha", "Slow", 9_000.0)
        _room_with_win(registry, "Beta", "Fast", 1_000.0)
        _room_with_win(registry, "Gamma", "Middle", 4_000.0)

        board = registry.global_escape_leaderboard()

        assert [entry["elapsedMs"] for entry in board] == [1_000.0, 4_000.0, 9_000.0]

    def test_entries_carry_their_source_room_id_and_name(self):
        # A global board is meaningless without saying which room was
        # escaped -- times are not comparable across different rooms
        # otherwise.
        registry = RoomsRegistry()
        room_id = _room_with_win(registry, "Alpha", "Alice", 5_000.0)

        entry = registry.global_escape_leaderboard()[0]

        assert entry["roomId"] == room_id
        assert entry["roomName"] == "Alpha"

    def test_respects_the_limit(self):
        registry = RoomsRegistry()
        for i in range(5):
            _room_with_win(registry, f"Room {i}", f"Player {i}", float(1_000 * (i + 1)))

        assert len(registry.global_escape_leaderboard(limit=3)) == 3

    def test_limit_selects_the_globally_fastest_not_the_first_rooms_found(self):
        registry = RoomsRegistry()
        _room_with_win(registry, "Alpha", "Slow", 9_000.0)
        _room_with_win(registry, "Beta", "Fast", 1_000.0)

        board = registry.global_escape_leaderboard(limit=1)

        assert [entry["displayName"] for entry in board] == ["Fast"]

    def test_includes_multiple_wins_from_the_same_room(self):
        registry = RoomsRegistry()
        room_id = _room_with_win(registry, "Alpha", "Alice", 5_000.0)
        builder = registry.get_builder(room_id)
        builder.start_escape_session("Bob", now_ms=0.0)
        builder._escape.mark_won("Bob", "Bob", now_ms=2_000.0)

        board = registry.global_escape_leaderboard()

        assert [entry["displayName"] for entry in board] == ["Bob", "Alice"]

    def test_rooms_without_escape_mode_contribute_nothing(self):
        registry = RoomsRegistry()
        registry.create_room(host_id="h1", name="Plain Room")
        _room_with_win(registry, "Alpha", "Alice", 5_000.0)

        assert len(registry.global_escape_leaderboard()) == 1

    def test_a_deleted_room_stops_contributing_entries(self):
        registry = RoomsRegistry()
        room_id = _room_with_win(registry, "Alpha", "Alice", 5_000.0)
        registry.rooms.pop(room_id)
        registry.room_builders.pop(room_id)

        assert registry.global_escape_leaderboard() == []

    def test_non_positive_limit_falls_back_to_the_default(self):
        registry = RoomsRegistry()
        _room_with_win(registry, "Alpha", "Alice", 5_000.0)

        assert len(registry.global_escape_leaderboard(limit=0)) == 1
