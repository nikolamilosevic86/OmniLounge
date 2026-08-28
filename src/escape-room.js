/**
 * Pure client-side helpers for the Escape Room feature (design doc
 * feature_designs/escape_room_feature_design.md §9/§10). No DOM/socket
 * access here -- all wiring lives in client/js/main.js, mirroring the
 * src/story.js and src/media.js split already used for every other
 * feature in this codebase.
 */

export const ESCAPE_STATE_LABELS = {
  not_started: 'Not Started',
  in_progress: 'In Progress',
  won: 'Escaped!',
  expired: "Time's Up",
};

/** Friendly label for an EscapeSessionEngine state, falling back to the raw value. */
export function escapeStatusLabel(state) {
  return ESCAPE_STATE_LABELS[state] ?? state;
}

/** Formats milliseconds remaining as "MM:SS", clamped at 00:00 and never negative. */
export function formatCountdown(remainingMs) {
  const totalSeconds = Math.max(0, Math.floor((remainingMs ?? 0) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

/** Whether the countdown chip should show its low-time warning treatment. */
export function isLowTime(remainingMs, thresholdMs = 30_000) {
  return remainingMs != null && remainingMs > 0 && remainingMs <= thresholdMs;
}

/** User-facing feedback for a room:puzzle:attempt result. Never echoes the answer. */
export function puzzleAttemptMessage(result) {
  if (!result) return '';
  if (result.alreadySolved) return "You've already solved this puzzle.";
  if (result.locked) return 'No attempts remaining. Ask the room host to reset this puzzle.';
  if (result.correct) return 'Correct!';
  const remaining = result.attemptsRemaining;
  if (remaining == null) return 'Not quite. Try again.';
  if (remaining <= 0) return 'Incorrect. No attempts remaining.';
  return `Incorrect. ${remaining} attempt${remaining === 1 ? '' : 's'} remaining.`;
}

/** Formats one leaderboard entry as "1. Alice — 02:15". */
export function formatLeaderboardEntry(entry, rank) {
  const name = entry?.displayName || 'Anonymous';
  return `${rank}. ${name} — ${formatCountdown(entry?.elapsedMs)}`;
}

/** User-facing feedback for a room:object:interact result on an escape_door. */
export function doorAttemptMessage(payload) {
  if (!payload) return '';
  if (payload.alreadyOpen) return 'The door is already open.';
  if (payload.opened) return 'The door opens.';
  return "It won't budge yet -- you're missing something.";
}
