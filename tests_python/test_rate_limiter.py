import pytest

from server.game.rate_limiter import SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    def setup_method(self):
        self.limiter = SlidingWindowRateLimiter(max_requests=3, window_ms=1000.0)

    def test_allows_requests_up_to_max_within_window(self):
        assert self.limiter.allow("user-1", now_ms=0) is True
        assert self.limiter.allow("user-1", now_ms=100) is True
        assert self.limiter.allow("user-1", now_ms=200) is True

    def test_blocks_request_exceeding_max_within_window(self):
        self.limiter.allow("user-1", now_ms=0)
        self.limiter.allow("user-1", now_ms=100)
        self.limiter.allow("user-1", now_ms=200)
        assert self.limiter.allow("user-1", now_ms=300) is False

    def test_allows_again_once_oldest_hit_falls_outside_window(self):
        self.limiter.allow("user-1", now_ms=0)
        self.limiter.allow("user-1", now_ms=100)
        self.limiter.allow("user-1", now_ms=200)
        assert self.limiter.allow("user-1", now_ms=300) is False
        # The hit at now_ms=0 is now outside the 1000ms window measured from 1001.
        assert self.limiter.allow("user-1", now_ms=1001) is True

    def test_separate_keys_are_tracked_independently(self):
        self.limiter.allow("user-1", now_ms=0)
        self.limiter.allow("user-1", now_ms=0)
        self.limiter.allow("user-1", now_ms=0)
        assert self.limiter.allow("user-1", now_ms=0) is False
        assert self.limiter.allow("user-2", now_ms=0) is True

    def test_blocked_request_is_not_recorded_as_a_hit(self):
        self.limiter.allow("user-1", now_ms=0)
        self.limiter.allow("user-1", now_ms=0)
        self.limiter.allow("user-1", now_ms=0)
        assert self.limiter.allow("user-1", now_ms=0) is False
        # Still blocked immediately after — the rejected call above must not
        # have evicted an old hit or been counted as a new one.
        assert self.limiter.allow("user-1", now_ms=0) is False

    def test_reset_clears_history_for_a_key(self):
        self.limiter.allow("user-1", now_ms=0)
        self.limiter.allow("user-1", now_ms=0)
        self.limiter.allow("user-1", now_ms=0)
        assert self.limiter.allow("user-1", now_ms=0) is False
        self.limiter.reset("user-1")
        assert self.limiter.allow("user-1", now_ms=0) is True

    def test_invalid_max_requests_raises(self):
        with pytest.raises(ValueError):
            SlidingWindowRateLimiter(max_requests=0, window_ms=1000.0)

    def test_invalid_window_ms_raises(self):
        with pytest.raises(ValueError):
            SlidingWindowRateLimiter(max_requests=3, window_ms=0)
