"""Pure, in-memory latency/error/usage metrics collector.

Kept dependency-free (no socketio/FastAPI imports) so it can be unit tested
directly. server/main.py wires this into socket event handling to power the
`/metrics` observability endpoint.
"""

from __future__ import annotations

from typing import Any


class MetricsCollector:
    """Accumulates per-event-name count/error/latency stats."""

    def __init__(self) -> None:
        self._events: dict[str, dict[str, float]] = {}

    def record(self, name: str, duration_ms: float, success: bool = True) -> None:
        if duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        stats = self._events.setdefault(
            name,
            {"count": 0, "error_count": 0, "total_ms": 0.0, "max_ms": 0.0},
        )
        stats["count"] += 1
        if not success:
            stats["error_count"] += 1
        stats["total_ms"] += duration_ms
        stats["max_ms"] = max(stats["max_ms"], duration_ms)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for name, stats in self._events.items():
            count = stats["count"]
            result[name] = {
                "count": int(count),
                "error_count": int(stats["error_count"]),
                "avg_latency_ms": stats["total_ms"] / count if count else 0.0,
                "max_latency_ms": stats["max_ms"],
            }
        return result
