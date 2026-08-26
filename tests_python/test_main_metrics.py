import pytest

import server.main as main_module


class FakeSio:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data=None, room=None, skip_sid=None):
        self.emitted.append((event, data, room))


@pytest.fixture(autouse=True)
def isolate_state(monkeypatch):
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)
    monkeypatch.setattr(main_module, "sio", FakeSio())

    from server.game.metrics import MetricsCollector

    fresh_metrics = MetricsCollector()
    monkeypatch.setattr(main_module, "metrics", fresh_metrics)
    return fresh_rooms, fresh_metrics


class TestMetricsInstrumentation:
    async def test_room_list_handler_still_runs_and_returns_no_error(self, isolate_state):
        # The metrics-instrumentation wrapper around sio.on() must not change
        # observable handler behavior for existing callers/tests.
        await main_module.room_list("alice", {})
        fresh_rooms, fresh_metrics = isolate_state
        assert main_module.sio.emitted[0][0] == "room:list"

    async def test_get_metrics_returns_snapshot_and_usage_counts(self, isolate_state):
        fresh_rooms, fresh_metrics = isolate_state
        fresh_metrics.record("room:list", 3.0)
        result = await main_module.get_metrics()
        assert result["events"]["room:list"]["count"] == 1
        assert result["rooms_active"] == len(fresh_rooms.rooms)
        assert result["players_connected"] == len(fresh_rooms.player_room)
