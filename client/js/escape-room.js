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

// ── Phase 3: templates, analytics, global leaderboard (design doc §14) ──

/**
 * Formats one cross-room leaderboard entry as "1. Alice — 02:15 · The Vault".
 * The room name matters here in a way it doesn't for a per-room board:
 * escape times from different rooms aren't comparable without it.
 */
export function formatGlobalLeaderboardEntry(entry, rank) {
  const base = formatLeaderboardEntry(entry, rank);
  return entry?.roomName ? `${base} · ${entry.roomName}` : base;
}

/**
 * Maps a puzzle template (from room:puzzle:templates) onto the authoring
 * form's field values. Deliberately never returns an `answer`: the whole
 * point of a template is to save typing on the *scaffolding*, while the
 * creator still picks a secret of their own. `answerPlaceholder` is only a
 * hint shown in the empty input.
 *
 * A null template means "custom", which blanks the form.
 */
export function puzzleTemplateFormValues(template) {
  if (!template) return { prompt: '', hints: '', matchMode: 'exact', answerPlaceholder: '' };
  return {
    prompt: template.promptTemplate ?? '',
    hints: (template.hints ?? []).join('\n'),
    matchMode: template.matchMode ?? 'exact',
    answerPlaceholder: template.answerPlaceholder ?? '',
  };
}

/** One-line summary of a puzzle's attempt analytics for the builder panel. */
export function formatPuzzleAnalytics(stats) {
  if (!stats) return '';
  if (!stats.totalAttempts) return 'No attempts yet';
  const percent = Math.round((stats.successRate ?? 0) * 100);
  const attempts = `${stats.totalAttempts} attempt${stats.totalAttempts === 1 ? '' : 's'}`;
  const hints = `${stats.hintsRequested ?? 0} hint${stats.hintsRequested === 1 ? '' : 's'}`;
  return `${attempts} · ${percent}% solved · ${hints}`;
}

/** Minimum attempts before a success rate is treated as meaningful. */
export const DIFFICULTY_SAMPLE_THRESHOLD = 3;

/**
 * Coarse difficulty band for a puzzle, for the creator-facing panel.
 * Below `DIFFICULTY_SAMPLE_THRESHOLD` attempts it stays 'unplayed' rather
 * than branding a puzzle "hard" off one unlucky guess.
 */
export function puzzleDifficultySignal(stats) {
  if (!stats || (stats.totalAttempts ?? 0) < DIFFICULTY_SAMPLE_THRESHOLD) return 'unplayed';
  const rate = stats.successRate ?? 0;
  if (rate >= 0.7) return 'easy';
  if (rate >= 0.25) return 'balanced';
  return 'hard';
}
