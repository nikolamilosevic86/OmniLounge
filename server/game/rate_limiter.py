"""Phase J: abuse-protection primitive — a simple sliding-window rate
limiter for expensive/paid actions (e.g. generative AI requests).

Pure, in-memory, dependency-free so it can be unit tested without real
time. Callers supply `now_ms` explicitly for deterministic testing,
following the same convention as the rest of server/game/*.py (e.g.
`RoomBuilderState.interact_with_object`).
"""

from collections import deque


class SlidingWindowRateLimiter:
    """Tracks hit timestamps per key and allows up to `max_requests` hits
    within any trailing `window_ms` window."""

    def __init__(self, max_requests: int, window_ms: float) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        self._max_requests = max_requests
        self._window_ms = window_ms
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, now_ms: float) -> bool:
        """Return True and record a hit if `key` is under its limit for the
        trailing window ending at `now_ms`; otherwise return False without
        recording anything."""
        timestamps = self._hits.setdefault(key, deque())
        cutoff = now_ms - self._window_ms
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= self._max_requests:
            return False
        timestamps.append(now_ms)
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)
