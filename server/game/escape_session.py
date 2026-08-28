"""Escape room feature: per-room, per-visitor session timer, win/lose state,
and leaderboard.

Pure, in-memory engine (design doc §8.1), following the same dict-backed
engine pattern as `PuzzleEngine`/`InventoryEngine`. Timers and progress
flags are tracked per-user (never room-wide) because OmniLounge rooms are
persistent, ambient multiplayer spaces rather than a booked, synchronized
physical session -- a visitor who joins mid-session must not inherit
someone else's countdown, revealed items, or opened doors (design doc §3.1).
Room-wide "Team/Shared Mode" is scoped to Phase 2 (§14).

Callers supply `now_ms` explicitly (no internal `time.time()` calls),
following the same convention as the rest of `server/game/*.py`.
"""

from typing import Any, Literal

SessionState = Literal["not_started", "in_progress", "won", "expired"]


class EscapeSessionEngine:
    """One instance per room, owned by `RoomBuilderState` exactly like
    `PuzzleEngine`/`InventoryEngine`."""

    def __init__(self) -> None:
        self._enabled: bool = False
        self._time_limit_ms: float | None = None
        self._briefing: str | None = None
        self._sessions: dict[str, dict[str, Any]] = {}  # user_id -> {"state", "startMs"}
        self._revealed: dict[str, set[str]] = {}  # user_id -> set of revealed hidden_item object ids
        self._opened: dict[str, set[str]] = {}  # user_id -> set of opened escape_door object ids
        self._attempts: list[dict[str, Any]] = []  # ordered leaderboard entries (§8.4)

    def configure(self, enabled: bool, time_limit_ms: float, briefing: str | None) -> None:
        if time_limit_ms <= 0:
            raise ValueError("time_limit_ms must be positive")
        self._enabled = enabled
        self._time_limit_ms = time_limit_ms
        self._briefing = briefing

    def get_briefing(self) -> str | None:
        return self._briefing

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise PermissionError("escape mode is not enabled for this room")

    def start(self, user_id: str, now_ms: float) -> dict[str, Any]:
        """Per-user attempt clock. A no-op returning the current status if
        already in_progress, so a visitor double-clicking Start (or
        reconnecting mid-session) can never reset their own clock back to
        full time (§16 Q2 covers the separate, explicit reset flow)."""
        self._require_enabled()
        session = self._sessions.get(user_id)
        if session is None or session["state"] != "in_progress":
            self._sessions[user_id] = {"state": "in_progress", "startMs": now_ms}
        return self.status(user_id, now_ms)

    def status(self, user_id: str, now_ms: float) -> dict[str, Any]:
        session = self._sessions.get(user_id)
        if session is None:
            return {"state": "not_started", "remainingMs": self._time_limit_ms}
        state = session["state"]
        if state == "in_progress":
            elapsed = now_ms - session["startMs"]
            remaining = max(self._time_limit_ms - elapsed, 0.0)
            return {"state": "in_progress", "remainingMs": remaining}
        return {"state": state, "remainingMs": 0.0}

    def expire_overdue_sessions(self, now_ms: float) -> list[str]:
        """Transition every user whose in_progress session has exceeded the
        configured time limit to `expired`, returning the list of user_ids
        just transitioned so the caller (`server/main.py`'s
        `tick_escape_sessions`, §8.2) can emit a targeted
        `room:escape:expired` event to exactly those users, mirroring
        `room:npc:moved`'s per-recipient broadcast rather than a full-room
        rebroadcast."""
        expired_user_ids = []
        for user_id, session in self._sessions.items():
            if session["state"] != "in_progress":
                continue
            elapsed = now_ms - session["startMs"]
            if elapsed >= self._time_limit_ms:
                session["state"] = "expired"
                expired_user_ids.append(user_id)
        return expired_user_ids

    def mark_won(self, user_id: str, display_name: str, now_ms: float) -> dict[str, Any]:
        """Called once, when the visitor's session transitions
        in_progress -> won. Computes elapsed_ms from this session's own
        start_ms and calls `record_attempt` itself, so callers never
        separately compute elapsed time or forget to record a leaderboard
        entry. A no-op (besides returning the current status) unless the
        session is currently in_progress -- expiry blocks winning, but not
        the mechanical act of opening the door itself (§8.3)."""
        session = self._sessions.get(user_id)
        if session is None or session["state"] != "in_progress":
            return self.status(user_id, now_ms)
        elapsed_ms = now_ms - session["startMs"]
        session["state"] = "won"
        self.record_attempt(user_id, display_name, elapsed_ms)
        return self.status(user_id, now_ms)

    def record_attempt(self, user_id: str, display_name: str, elapsed_ms: float) -> None:
        """Appended to an ordered leaderboard list, same append-then-sort
        pattern as `RoomBuilderState._versions`. Invoked only from
        `mark_won`."""
        session = self._sessions.get(user_id)
        completed_at_ms = session["startMs"] + elapsed_ms if session is not None else elapsed_ms
        self._attempts.append({
            "displayName": display_name,
            "elapsedMs": elapsed_ms,
            "completedAtMs": completed_at_ms,
        })

    def leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        return sorted(self._attempts, key=lambda entry: entry["elapsedMs"])[:limit]

    def reset(self, user_id: str) -> None:
        """Clears this visitor's timer plus every per-visitor flag below
        (reveal/open state). Only callable when that visitor's own state is
        "not_started" or "expired" -- resetting an "in_progress" (or "won")
        session is rejected (PermissionError) so a visitor can never use
        reset to dodge a bad guess's rate limit or claim a fresh leaderboard
        run mid-attempt (§9, §16 Q2)."""
        session = self._sessions.get(user_id)
        if session is not None and session["state"] not in ("not_started", "expired"):
            raise PermissionError(f"cannot reset a session in state: {session['state']}")
        self._sessions.pop(user_id, None)
        self._revealed.pop(user_id, None)
        self._opened.pop(user_id, None)

    # ── Per-visitor live progress (§3.1) ──────────────────────────────────
    # Kept here, alongside the timer, rather than on the objects themselves,
    # mirroring StoryEngine's separation of node definitions from
    # `_progress`. Independent of `_enabled`/timer state: a creator can gate
    # content behind escape_door/hidden_item without ever configuring the
    # timer/leaderboard subsystem at all (§8.3).

    def reveal_item(self, user_id: str, object_id: str) -> None:
        self._revealed.setdefault(user_id, set()).add(object_id)

    def has_revealed(self, user_id: str, object_id: str) -> bool:
        return object_id in self._revealed.get(user_id, set())

    def open_door(self, user_id: str, object_id: str) -> None:
        self._opened.setdefault(user_id, set()).add(object_id)

    def has_opened(self, user_id: str, object_id: str) -> bool:
        return object_id in self._opened.get(user_id, set())

    def clear_revealed_for_object(self, object_id: str) -> None:
        """Remove `object_id` from every visitor's revealed set. Used when
        the `hidden_item` object is deleted (§5.3), so a recycled object id
        doesn't inherit a stale "already revealed" flag from before it was
        deleted."""
        for revealed in self._revealed.values():
            revealed.discard(object_id)

    def clear_opened_for_object(self, object_id: str) -> None:
        """Remove `object_id` from every visitor's opened set. Used when the
        `escape_door` object is deleted (§5.3), for the same reason as
        `clear_revealed_for_object`."""
        for opened in self._opened.values():
            opened.discard(object_id)
