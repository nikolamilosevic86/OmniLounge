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

/**
 * View-model for the puzzle template picker's elevated-card row (design doc
 * build_mode_ui_redesign_feature_design.md §8.7, Gap 3), replacing the old
 * bare `<option>` list so a template's `description` is no longer discarded.
 * Always leads with a "Custom (blank)" card so a creator can start from an
 * empty form -- `puzzleTemplateFormValues(null)` already implements that
 * behavior once selected. `active` marks exactly one card: the one whose
 * `templateId` equals `selectedTemplateId` (or Custom, when it's blank).
 * Each card carries the template's paired `propType` (escape_room_feature_design.md
 * §5.4) so the card can preview the shape the puzzle will wear, and so
 * choosing a template can pre-select that shape in the picker.
 */
export function puzzleTemplateCardOptions(templates, selectedTemplateId = '') {
  const customCard = {
    templateId: '',
    label: 'Custom (blank)',
    description: 'Start from a blank puzzle.',
    // Deliberately blank: a blank puzzle shouldn't inherit some other
    // archetype's shape, it picks its own from the shape picker.
    propType: '',
    active: !selectedTemplateId,
  };
  const templateCards = (templates || []).map((t) => ({
    templateId: t.templateId,
    label: t.label,
    description: t.description || '',
    propType: t.propType || '',
    active: t.templateId === selectedTemplateId,
  }));
  return [customCard, ...templateCards];
}

/**
 * The puzzle prop shapes a creator can choose from (escape_room_feature_design.md
 * §5.4), mirroring `PUZZLE_PROP_TYPES` in server/game/room_object_catalog.py --
 * same ids, same order, so the shape picker and the builder catalog agree.
 * The descriptions say what each shape *reads as* from across the room, which
 * is the whole point of giving a puzzle a body.
 */
export const PUZZLE_PROP_SHAPES = [
  { propType: 'cipher_box', label: 'Cipher Box', description: 'Stacked glyph rings -- reads as a coded message.' },
  { propType: 'digital_lock', label: 'Digital Lock', description: 'Keypad and LED display -- reads as a numeric code.' },
  { propType: 'combination_dial', label: 'Combination Dial', description: 'A safe dial -- reads as a sequence to turn through.' },
  { propType: 'riddle_tablet', label: 'Riddle Tablet', description: 'An engraved standing stone -- reads as words to solve.' },
  { propType: 'clue_board', label: 'Clue Board', description: 'Pinned notes and red string -- reads as clues to connect.' },
];

/**
 * View-model for the puzzle shape picker. Leads with a "No shape" card because
 * a puzzle is still perfectly valid bodiless -- it can be bound to any
 * existing object by hand -- and marks exactly one card active. An unknown or
 * missing `selectedPropType` falls back to "No shape" rather than leaving the
 * row with nothing selected, so the picker can never render in a state the
 * creator can't interpret.
 */
export function puzzlePropCardOptions(selectedPropType = '') {
  const known = PUZZLE_PROP_SHAPES.some((s) => s.propType === selectedPropType);
  const selected = known ? selectedPropType : '';
  return [
    {
      propType: '',
      label: 'No shape',
      description: 'Bind this puzzle to an object yourself.',
      active: selected === '',
    },
    ...PUZZLE_PROP_SHAPES.map((shape) => ({ ...shape, active: shape.propType === selected })),
  ];
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

/** Client-side pre-check for the puzzle add/edit form (design doc
 * build_mode_ui_redesign_feature_design.md §8.7, Gap 1): a puzzle id and
 * answer are always required, and a prompt is required unless a template
 * (which supplies its own prompt template) is selected. Shared by the Add
 * and Save-Changes (edit) paths -- the server never echoes a puzzle's
 * answer back to the client, so this validation is also what forces a
 * fresh answer to be re-entered before an edit can be saved. */
export function validatePuzzleInput({ puzzleId, prompt, answer, templateId } = {}) {
  const trimmedId = (puzzleId || '').trim();
  const trimmedAnswer = (answer || '').trim();
  const trimmedPrompt = (prompt || '').trim();
  if (!trimmedId || !trimmedAnswer || (!trimmedPrompt && !templateId)) {
    return { valid: false, error: 'Puzzle ID, prompt, and answer are required.' };
  }
  return { valid: true, error: null };
}
