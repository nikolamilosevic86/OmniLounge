/**
 * Escape Room feature helpers.
 * (Client-side copy — src/escape-room.js is the canonical source used by tests.)
 */

export const ESCAPE_STATE_LABELS = {
  not_started: 'Not Started',
  in_progress: 'In Progress',
  won: 'Escaped!',
  expired: "Time's Up",
};

export function escapeStatusLabel(state) {
  return ESCAPE_STATE_LABELS[state] ?? state;
}

export function formatCountdown(remainingMs) {
  const totalSeconds = Math.max(0, Math.floor((remainingMs ?? 0) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

export function isLowTime(remainingMs, thresholdMs = 30_000) {
  return remainingMs != null && remainingMs > 0 && remainingMs <= thresholdMs;
}

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

export function formatLeaderboardEntry(entry, rank) {
  const name = entry?.displayName || 'Anonymous';
  return `${rank}. ${name} — ${formatCountdown(entry?.elapsedMs)}`;
}

export function doorAttemptMessage(payload) {
  if (!payload) return '';
  if (payload.alreadyOpen) return 'The door is already open.';
  if (payload.opened) return 'The door opens.';
  return "It won't budge yet -- you're missing something.";
}
