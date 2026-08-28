"""Escape room feature: puzzle domain logic.

Pure, in-memory, per-room puzzle store, following the same "library" engine
pattern as `BookshelfLibrary`/`MediaLibrary`/`StoryEngine`/`GuideEngine`
(dict-backed state, no I/O, fully unit-testable without sockets or a DB).

Design: feature_designs/escape_room_feature_design.md §6.1.

Puzzle-solved state, hint usage, and attempt counts are all tracked
per-(puzzle_id, user_id) -- never globally per puzzle -- so multiple
visitors can independently attempt (and independently get stuck on) the
same room concurrently without affecting each other (design doc §3.1).

The answer is only ever readable server-side: `get_puzzle_public` always
strips it, mirroring the same discipline `StoryEngine._public_character`
already applies to `apiKey`.
"""

from typing import Any

from server.game.rate_limiter import SlidingWindowRateLimiter

MATCH_MODES = {"exact", "numeric", "contains"}

# Abuse protection (same spirit as story.py's GENERATIVE_RATE_LIMIT_*): cap
# guess attempts per (puzzle, user) to a small burst per minute, blunting
# brute-force scripts against short numeric/word codes. This is separate
# from (and in addition to) an author-configured `max_attempts` lockout,
# which is a *permanent* (until reset) per-user cap, not a time-windowed one.
ATTEMPT_RATE_LIMIT_MAX_REQUESTS = 10
ATTEMPT_RATE_LIMIT_WINDOW_MS = 60_000.0


def _normalize(text: str) -> str:
    return text.strip().casefold()


def _answers_match(match_mode: str, answer: str, guess: str) -> bool:
    if match_mode == "exact":
        return _normalize(guess) == _normalize(answer)
    if match_mode == "numeric":
        try:
            return float(guess.strip()) == float(answer.strip())
        except (TypeError, ValueError):
            return False
    if match_mode == "contains":
        return _normalize(answer) in _normalize(guess)
    raise ValueError(f"invalid match_mode: {match_mode}")


class PuzzleEngine:
    """In-memory per-room puzzle definitions and per-user solve/hint/attempt
    state."""

    def __init__(self) -> None:
        self._puzzles: dict[str, dict[str, Any]] = {}
        self._solved_by: dict[str, set[str]] = {}
        self._hints_used: dict[tuple[str, str], int] = {}
        self._attempt_counts: dict[tuple[str, str], int] = {}
        self._attempt_limiter = SlidingWindowRateLimiter(
            max_requests=ATTEMPT_RATE_LIMIT_MAX_REQUESTS, window_ms=ATTEMPT_RATE_LIMIT_WINDOW_MS,
        )

    def _require_puzzle(self, puzzle_id: str) -> dict[str, Any]:
        record = self._puzzles.get(puzzle_id)
        if record is None:
            raise KeyError(f"unknown puzzle: {puzzle_id}")
        return record

    def add_puzzle(
        self,
        puzzle_id: str,
        prompt: str,
        answer: str,
        hints: list[str] | None = None,
        reveal_item_id: str | None = None,
        unlock_door_id: str | None = None,
        match_mode: str = "exact",
        max_attempts: int | None = None,
    ) -> dict[str, Any]:
        if puzzle_id in self._puzzles:
            raise ValueError(f"puzzle id already exists: {puzzle_id}")
        if not prompt or not prompt.strip():
            raise ValueError("prompt is required")
        if not answer or not answer.strip():
            raise ValueError("answer is required")
        if match_mode not in MATCH_MODES:
            raise ValueError(f"match_mode must be one of {sorted(MATCH_MODES)}, got {match_mode!r}")
        if max_attempts is not None and max_attempts <= 0:
            raise ValueError("max_attempts must be positive when set")
        record = {
            "puzzleId": puzzle_id,
            "prompt": prompt,
            "answer": answer,
            "hints": list(hints or []),
            "revealItemId": reveal_item_id,
            "unlockDoorId": unlock_door_id,
            "matchMode": match_mode,
            "maxAttempts": max_attempts,
        }
        self._puzzles[puzzle_id] = record
        return self.get_puzzle_public(puzzle_id)

    def remove_puzzle(self, puzzle_id: str) -> bool:
        if puzzle_id not in self._puzzles:
            return False
        del self._puzzles[puzzle_id]
        self._solved_by.pop(puzzle_id, None)
        for key in [k for k in self._hints_used if k[0] == puzzle_id]:
            del self._hints_used[key]
        for key in [k for k in self._attempt_counts if k[0] == puzzle_id]:
            del self._attempt_counts[key]
        return True

    def get_puzzle_public(self, puzzle_id: str) -> dict[str, Any]:
        record = self._require_puzzle(puzzle_id)
        return {k: v for k, v in record.items() if k != "answer"}

    def list_puzzles(self) -> list[dict[str, Any]]:
        return [self.get_puzzle_public(puzzle_id) for puzzle_id in self._puzzles]

    def is_solved(self, puzzle_id: str, user_id: str) -> bool:
        return user_id in self._solved_by.get(puzzle_id, set())

    def _attempts_remaining(self, record: dict[str, Any], count_key: tuple[str, str]) -> int | None:
        max_attempts = record["maxAttempts"]
        if max_attempts is None:
            return None
        used = self._attempt_counts.get(count_key, 0)
        return max(max_attempts - used, 0)

    def attempt_solve(self, puzzle_id: str, user_id: str, guess: str, now_ms: float) -> dict[str, Any]:
        record = self._require_puzzle(puzzle_id)
        count_key = (puzzle_id, user_id)

        if self.is_solved(puzzle_id, user_id):
            return {
                "correct": True,
                "attemptsRemaining": self._attempts_remaining(record, count_key),
                "alreadySolved": True,
                "locked": False,
            }

        max_attempts = record["maxAttempts"]
        if max_attempts is not None and self._attempt_counts.get(count_key, 0) >= max_attempts:
            return {"correct": False, "attemptsRemaining": 0, "alreadySolved": False, "locked": True}

        if not self._attempt_limiter.allow(f"{puzzle_id}:{user_id}", now_ms):
            # A rate-limited guess is never evaluated at all, so it must not
            # consume an authored max_attempts slot -- that would silently
            # double-penalize a fast-typing legitimate visitor on top of the
            # rate limit itself.
            return {
                "correct": False,
                "attemptsRemaining": self._attempts_remaining(record, count_key),
                "alreadySolved": False,
                "locked": False,
            }

        if _answers_match(record["matchMode"], record["answer"], guess):
            self._solved_by.setdefault(puzzle_id, set()).add(user_id)
            return {
                "correct": True,
                "attemptsRemaining": self._attempts_remaining(record, count_key),
                "alreadySolved": False,
                "locked": False,
            }

        self._attempt_counts[count_key] = self._attempt_counts.get(count_key, 0) + 1
        now_locked = max_attempts is not None and self._attempt_counts[count_key] >= max_attempts
        return {
            "correct": False,
            "attemptsRemaining": self._attempts_remaining(record, count_key),
            "alreadySolved": False,
            "locked": now_locked,
        }

    def reset_attempts(self, puzzle_id: str, user_id: str) -> None:
        """Edit-permission-gated recovery path (room:puzzle:reset): clears a
        locked-out user's attempt count and rate-limit window only -- their
        solved state (if any) is never touched, so a solved puzzle can never
        be "un-solved" by a reset (design doc §6.1)."""
        self._require_puzzle(puzzle_id)
        self._attempt_counts.pop((puzzle_id, user_id), None)
        self._attempt_limiter.reset(f"{puzzle_id}:{user_id}")

    def request_hint(self, puzzle_id: str, user_id: str, now_ms: float) -> dict[str, Any]:
        record = self._require_puzzle(puzzle_id)
        hints = record["hints"]
        key = (puzzle_id, user_id)
        used = self._hints_used.get(key, 0)
        if used >= len(hints):
            return {"hint": None, "hintsUsed": used, "hintsRemaining": 0}
        hint = hints[used]
        self._hints_used[key] = used + 1
        return {"hint": hint, "hintsUsed": used + 1, "hintsRemaining": len(hints) - (used + 1)}
