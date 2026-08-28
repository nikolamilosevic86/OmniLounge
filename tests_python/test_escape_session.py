import pytest

from server.game.escape_session import EscapeSessionEngine


def make_engine(time_limit_ms=60_000.0, enabled=True, briefing="Find the way out."):
    engine = EscapeSessionEngine()
    engine.configure(enabled=enabled, time_limit_ms=time_limit_ms, briefing=briefing)
    return engine


class TestConfigure:
    def test_rejects_non_positive_time_limit(self):
        engine = EscapeSessionEngine()
        with pytest.raises(ValueError, match="time_limit_ms"):
            engine.configure(enabled=True, time_limit_ms=0, briefing=None)

    def test_status_before_any_configure_is_not_started_with_no_known_limit(self):
        engine = EscapeSessionEngine()
        status = engine.status("u1", now_ms=0.0)
        assert status == {"state": "not_started", "remainingMs": None}


class TestStart:
    def test_start_requires_enabled_configuration(self):
        engine = make_engine(enabled=False)
        with pytest.raises(PermissionError):
            engine.start("u1", now_ms=0.0)

    def test_start_transitions_to_in_progress_with_full_time_remaining(self):
        engine = make_engine(time_limit_ms=60_000.0)
        result = engine.start("u1", now_ms=1_000.0)
        assert result == {"state": "in_progress", "remainingMs": 60_000.0}

    def test_start_is_idempotent_and_does_not_reset_the_clock(self):
        engine = make_engine(time_limit_ms=60_000.0)
        engine.start("u1", now_ms=0.0)
        # Elapse 10s, then call start again (e.g. a double-click or a
        # reconnect) -- this must NOT reset the visitor's clock back to full.
        second = engine.start("u1", now_ms=10_000.0)
        assert second == {"state": "in_progress", "remainingMs": 50_000.0}

    def test_starting_is_isolated_per_user(self):
        engine = make_engine(time_limit_ms=60_000.0)
        engine.start("u1", now_ms=0.0)
        assert engine.status("u2", now_ms=0.0) == {"state": "not_started", "remainingMs": 60_000.0}


class TestStatus:
    def test_not_started_reports_full_configured_time(self):
        engine = make_engine(time_limit_ms=30_000.0)
        assert engine.status("u1", now_ms=500.0) == {"state": "not_started", "remainingMs": 30_000.0}

    def test_in_progress_remaining_time_decreases(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        assert engine.status("u1", now_ms=20_000.0) == {"state": "in_progress", "remainingMs": 10_000.0}

    def test_remaining_time_floors_at_zero_without_auto_expiring(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        status = engine.status("u1", now_ms=999_999.0)
        assert status == {"state": "in_progress", "remainingMs": 0.0}


class TestExpireOverdueSessions:
    def test_transitions_overdue_in_progress_sessions_to_expired(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        expired = engine.expire_overdue_sessions(now_ms=30_001.0)
        assert expired == ["u1"]
        assert engine.status("u1", now_ms=99_999.0) == {"state": "expired", "remainingMs": 0.0}

    def test_does_not_touch_sessions_still_within_the_limit(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        expired = engine.expire_overdue_sessions(now_ms=1_000.0)
        assert expired == []
        assert engine.status("u1", now_ms=1_000.0)["state"] == "in_progress"

    def test_ignores_not_started_and_already_finished_sessions(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        engine.mark_won("u1", "Alice", now_ms=1_000.0)
        expired = engine.expire_overdue_sessions(now_ms=99_999.0)
        assert expired == []
        assert engine.status("u1", now_ms=99_999.0)["state"] == "won"


class TestMarkWon:
    def test_marks_won_and_records_leaderboard_entry(self):
        engine = make_engine(time_limit_ms=60_000.0)
        engine.start("u1", now_ms=0.0)
        result = engine.mark_won("u1", "Alice", now_ms=15_000.0)
        assert result == {"state": "won", "remainingMs": 0.0}
        board = engine.leaderboard()
        assert len(board) == 1
        assert board[0]["displayName"] == "Alice"
        assert board[0]["elapsedMs"] == 15_000.0
        assert board[0]["completedAtMs"] == 15_000.0

    def test_is_a_no_op_when_session_already_expired(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        engine.expire_overdue_sessions(now_ms=30_001.0)
        result = engine.mark_won("u1", "Alice", now_ms=99_999.0)
        assert result["state"] == "expired"
        assert engine.leaderboard() == []

    def test_is_a_no_op_when_never_started(self):
        engine = make_engine(time_limit_ms=30_000.0)
        result = engine.mark_won("u1", "Alice", now_ms=1_000.0)
        assert result["state"] == "not_started"
        assert engine.leaderboard() == []


class TestLeaderboard:
    def test_sorted_fastest_first_and_respects_limit(self):
        engine = make_engine(time_limit_ms=60_000.0)
        engine.start("u1", now_ms=0.0)
        engine.mark_won("u1", "Slow", now_ms=50_000.0)
        engine.start("u2", now_ms=0.0)
        engine.mark_won("u2", "Fast", now_ms=5_000.0)
        board = engine.leaderboard(limit=1)
        assert len(board) == 1
        assert board[0]["displayName"] == "Fast"


class TestReset:
    def test_reset_from_not_started_is_a_no_op(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.reset("u1")  # must not raise
        assert engine.status("u1", now_ms=0.0)["state"] == "not_started"

    def test_reset_rejected_while_in_progress(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        with pytest.raises(PermissionError):
            engine.reset("u1")

    def test_reset_rejected_after_winning(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        engine.mark_won("u1", "Alice", now_ms=1_000.0)
        with pytest.raises(PermissionError):
            engine.reset("u1")

    def test_reset_allowed_after_expiry_and_clears_progress_flags(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        engine.reveal_item("u1", "item-1")
        engine.open_door("u1", "door-1")
        engine.expire_overdue_sessions(now_ms=30_001.0)
        engine.reset("u1")
        assert engine.status("u1", now_ms=30_001.0) == {"state": "not_started", "remainingMs": 30_000.0}
        assert engine.has_revealed("u1", "item-1") is False
        assert engine.has_opened("u1", "door-1") is False

    def test_reset_is_isolated_per_user(self):
        engine = make_engine(time_limit_ms=30_000.0)
        engine.start("u1", now_ms=0.0)
        engine.reveal_item("u1", "item-1")
        engine.start("u2", now_ms=0.0)
        engine.reveal_item("u2", "item-1")
        engine.expire_overdue_sessions(now_ms=30_001.0)
        engine.reset("u1")
        assert engine.has_revealed("u1", "item-1") is False
        assert engine.has_revealed("u2", "item-1") is True


class TestRevealAndOpenProgress:
    def test_reveal_item_defaults_to_false_and_is_per_user(self):
        engine = EscapeSessionEngine()
        assert engine.has_revealed("u1", "item-1") is False
        engine.reveal_item("u1", "item-1")
        assert engine.has_revealed("u1", "item-1") is True
        assert engine.has_revealed("u2", "item-1") is False

    def test_open_door_defaults_to_false_and_is_per_user(self):
        engine = EscapeSessionEngine()
        assert engine.has_opened("u1", "door-1") is False
        engine.open_door("u1", "door-1")
        assert engine.has_opened("u1", "door-1") is True
        assert engine.has_opened("u2", "door-1") is False

    def test_reveal_and_open_do_not_require_enabled_escape_mode(self):
        # Gameplay progress (reveal/open) must never be blocked by whether a
        # room host has enabled the timer/leaderboard subsystem (§8.3): a
        # creator can use escape_door/hidden_item purely as gated content
        # without ever configuring escape mode at all.
        engine = EscapeSessionEngine()
        engine.reveal_item("u1", "item-1")
        engine.open_door("u1", "door-1")
        assert engine.has_revealed("u1", "item-1") is True
        assert engine.has_opened("u1", "door-1") is True
