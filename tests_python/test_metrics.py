import pytest

from server.game.metrics import MetricsCollector


class TestMetricsCollector:
    def test_snapshot_is_empty_when_no_events_recorded(self):
        metrics = MetricsCollector()
        assert metrics.snapshot() == {}

    def test_records_single_success_event(self):
        metrics = MetricsCollector()
        metrics.record("player:move", 12.5)
        snapshot = metrics.snapshot()
        assert snapshot["player:move"]["count"] == 1
        assert snapshot["player:move"]["error_count"] == 0
        assert snapshot["player:move"]["avg_latency_ms"] == pytest.approx(12.5)
        assert snapshot["player:move"]["max_latency_ms"] == pytest.approx(12.5)

    def test_records_error_event_increments_count_and_error_count(self):
        metrics = MetricsCollector()
        metrics.record("chat:send", 5.0, success=False)
        snapshot = metrics.snapshot()
        assert snapshot["chat:send"]["count"] == 1
        assert snapshot["chat:send"]["error_count"] == 1

    def test_averages_latency_across_multiple_events(self):
        metrics = MetricsCollector()
        metrics.record("room:join", 10.0)
        metrics.record("room:join", 20.0)
        snapshot = metrics.snapshot()
        assert snapshot["room:join"]["count"] == 2
        assert snapshot["room:join"]["avg_latency_ms"] == pytest.approx(15.0)

    def test_tracks_max_latency_across_multiple_events(self):
        metrics = MetricsCollector()
        metrics.record("room:join", 10.0)
        metrics.record("room:join", 45.0)
        metrics.record("room:join", 20.0)
        snapshot = metrics.snapshot()
        assert snapshot["room:join"]["max_latency_ms"] == pytest.approx(45.0)

    def test_separate_event_names_are_tracked_independently(self):
        metrics = MetricsCollector()
        metrics.record("player:move", 1.0)
        metrics.record("chat:send", 2.0)
        snapshot = metrics.snapshot()
        assert set(snapshot.keys()) == {"player:move", "chat:send"}
        assert snapshot["player:move"]["count"] == 1
        assert snapshot["chat:send"]["count"] == 1

    def test_negative_duration_raises_value_error(self):
        metrics = MetricsCollector()
        with pytest.raises(ValueError):
            metrics.record("player:move", -1.0)

    def test_snapshot_returns_a_copy_not_live_reference(self):
        metrics = MetricsCollector()
        metrics.record("player:move", 1.0)
        snapshot = metrics.snapshot()
        snapshot["player:move"]["count"] = 999
        assert metrics.snapshot()["player:move"]["count"] == 1
