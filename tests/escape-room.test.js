import { describe, it, expect } from 'vitest';
import {
  escapeStatusLabel,
  formatCountdown,
  isLowTime,
  puzzleAttemptMessage,
  formatLeaderboardEntry,
  doorAttemptMessage,
  formatGlobalLeaderboardEntry,
  puzzleTemplateFormValues,
  formatPuzzleAnalytics,
  puzzleDifficultySignal,
  validatePuzzleInput,
  puzzleTemplateCardOptions,
  puzzlePropCardOptions,
} from '../src/escape-room.js';

describe('escapeStatusLabel', () => {
  it('maps known states to friendly labels', () => {
    expect(escapeStatusLabel('not_started')).toBe('Not Started');
    expect(escapeStatusLabel('in_progress')).toBe('In Progress');
    expect(escapeStatusLabel('won')).toBe('Escaped!');
    expect(escapeStatusLabel('expired')).toBe("Time's Up");
  });

  it('falls back to the raw value for an unknown state', () => {
    expect(escapeStatusLabel('mystery')).toBe('mystery');
  });
});

describe('formatCountdown', () => {
  it('formats whole minutes and seconds', () => {
    expect(formatCountdown(90_000)).toBe('01:30');
  });

  it('pads single-digit minutes and seconds', () => {
    expect(formatCountdown(65_000)).toBe('01:05');
  });

  it('floors partial seconds', () => {
    expect(formatCountdown(1_999)).toBe('00:01');
  });

  it('clamps negative values to zero', () => {
    expect(formatCountdown(-500)).toBe('00:00');
  });

  it('treats null/undefined as zero', () => {
    expect(formatCountdown(null)).toBe('00:00');
    expect(formatCountdown(undefined)).toBe('00:00');
  });
});

describe('isLowTime', () => {
  it('is false when remaining time is above the threshold', () => {
    expect(isLowTime(60_000, 30_000)).toBe(false);
  });

  it('is true when remaining time is at or below the threshold', () => {
    expect(isLowTime(30_000, 30_000)).toBe(true);
    expect(isLowTime(5_000, 30_000)).toBe(true);
  });

  it('is false at exactly zero (session already over, not "low time")', () => {
    expect(isLowTime(0, 30_000)).toBe(false);
  });

  it('is false when remainingMs is null/undefined', () => {
    expect(isLowTime(null)).toBe(false);
    expect(isLowTime(undefined)).toBe(false);
  });

  it('uses a default 30s threshold', () => {
    expect(isLowTime(29_000)).toBe(true);
    expect(isLowTime(31_000)).toBe(false);
  });
});

describe('puzzleAttemptMessage', () => {
  it('returns empty string for a falsy result', () => {
    expect(puzzleAttemptMessage(null)).toBe('');
  });

  it('reports already solved', () => {
    expect(puzzleAttemptMessage({ alreadySolved: true })).toBe("You've already solved this puzzle.");
  });

  it('reports locked out', () => {
    expect(puzzleAttemptMessage({ locked: true })).toBe(
      'No attempts remaining. Ask the room host to reset this puzzle.',
    );
  });

  it('reports a correct guess', () => {
    expect(puzzleAttemptMessage({ correct: true })).toBe('Correct!');
  });

  it('reports an incorrect guess with attempts remaining', () => {
    expect(puzzleAttemptMessage({ correct: false, attemptsRemaining: 2 })).toBe(
      'Incorrect. 2 attempts remaining.',
    );
  });

  it('uses singular "attempt" for exactly one remaining', () => {
    expect(puzzleAttemptMessage({ correct: false, attemptsRemaining: 1 })).toBe(
      'Incorrect. 1 attempt remaining.',
    );
  });

  it('reports no attempts remaining without a locked flag', () => {
    expect(puzzleAttemptMessage({ correct: false, attemptsRemaining: 0 })).toBe(
      'Incorrect. No attempts remaining.',
    );
  });

  it('falls back to a generic message when attemptsRemaining is unknown (unlimited attempts)', () => {
    expect(puzzleAttemptMessage({ correct: false, attemptsRemaining: null })).toBe('Not quite. Try again.');
  });
});

describe('formatLeaderboardEntry', () => {
  it('formats an entry with rank, name, and elapsed time', () => {
    expect(formatLeaderboardEntry({ displayName: 'Alice', elapsedMs: 135_000 }, 1)).toBe('1. Alice — 02:15');
  });

  it('falls back to "Anonymous" when displayName is missing', () => {
    expect(formatLeaderboardEntry({ elapsedMs: 60_000 }, 3)).toBe('3. Anonymous — 01:00');
  });
});

describe('doorAttemptMessage', () => {
  it('returns empty string for a falsy payload', () => {
    expect(doorAttemptMessage(null)).toBe('');
  });

  it('reports already open', () => {
    expect(doorAttemptMessage({ opened: true, alreadyOpen: true })).toBe('The door is already open.');
  });

  it('reports a fresh open', () => {
    expect(doorAttemptMessage({ opened: true, alreadyOpen: false })).toBe('The door opens.');
  });

  it('reports the door remains locked', () => {
    expect(doorAttemptMessage({ opened: false, alreadyOpen: false })).toBe(
      "It won't budge yet -- you're missing something.",
    );
  });
});

// ── Phase 3: templates, analytics, global leaderboard (design doc §14) ──

describe('formatGlobalLeaderboardEntry', () => {
  it('names the source room, since times are not comparable across rooms', () => {
    expect(formatGlobalLeaderboardEntry(
      { displayName: 'Alice', elapsedMs: 135_000, roomName: 'The Vault' }, 1,
    )).toBe('1. Alice — 02:15 · The Vault');
  });

  it('falls back to "Anonymous" when displayName is missing', () => {
    expect(formatGlobalLeaderboardEntry({ elapsedMs: 60_000, roomName: 'Attic' }, 2))
      .toBe('2. Anonymous — 01:00 · Attic');
  });

  it('omits the room suffix entirely when the room name is unknown', () => {
    expect(formatGlobalLeaderboardEntry({ displayName: 'Bo', elapsedMs: 60_000 }, 1))
      .toBe('1. Bo — 01:00');
  });
});

describe('puzzleTemplateFormValues', () => {
  const template = {
    templateId: 'number_lock',
    promptTemplate: 'Enter the 4-digit combination.',
    answerPlaceholder: '1234',
    matchMode: 'numeric',
    hints: ['It is even.', 'It starts with 1.'],
  };

  it('maps a template onto the authoring form fields', () => {
    expect(puzzleTemplateFormValues(template)).toEqual({
      prompt: 'Enter the 4-digit combination.',
      hints: 'It is even.\nIt starts with 1.',
      matchMode: 'numeric',
      answerPlaceholder: '1234',
    });
  });

  it('joins hints with newlines to match the textarea format the form submits', () => {
    expect(puzzleTemplateFormValues(template).hints).toBe('It is even.\nIt starts with 1.');
  });

  it('never prefills the answer, so a creator must author their own', () => {
    expect(puzzleTemplateFormValues(template)).not.toHaveProperty('answer');
  });

  it('returns blank fields for a missing template so "custom" clears the form', () => {
    expect(puzzleTemplateFormValues(null)).toEqual({
      prompt: '', hints: '', matchMode: 'exact', answerPlaceholder: '',
    });
  });

  it('tolerates a template with no hints', () => {
    expect(puzzleTemplateFormValues({ promptTemplate: 'p', matchMode: 'exact' }).hints).toBe('');
  });
});

describe('puzzleTemplateCardOptions (design doc build_mode_ui_redesign_feature_design.md section 8.7, Gap 3)', () => {
  const templates = [
    { templateId: 'riddle', label: 'Riddle', description: 'A word riddle with a single specific answer.', propType: 'riddle_tablet' },
    { templateId: 'cipher', label: 'Cipher', description: 'A coded message the player must decode into plain text.', propType: 'cipher_box' },
  ];

  it('always leads with a "Custom (blank)" card', () => {
    const cards = puzzleTemplateCardOptions(templates);
    expect(cards[0]).toEqual({
      templateId: '', label: 'Custom (blank)', description: 'Start from a blank puzzle.', propType: '', active: true,
    });
  });

  it('maps every template onto a card with its label and description', () => {
    const cards = puzzleTemplateCardOptions(templates);
    expect(cards.slice(1)).toEqual([
      { templateId: 'riddle', label: 'Riddle', description: 'A word riddle with a single specific answer.', propType: 'riddle_tablet', active: false },
      { templateId: 'cipher', label: 'Cipher', description: 'A coded message the player must decode into plain text.', propType: 'cipher_box', active: false },
    ]);
  });

  it('carries each template\'s paired prop shape so the card can preview it', () => {
    const cards = puzzleTemplateCardOptions(templates, 'cipher');
    expect(cards.find((c) => c.templateId === 'cipher').propType).toBe('cipher_box');
  });

  it('leaves the Custom card without a prop shape, since a blank puzzle picks its own', () => {
    expect(puzzleTemplateCardOptions(templates)[0].propType).toBe('');
  });

  it('marks the Custom card active when no template id is selected', () => {
    const cards = puzzleTemplateCardOptions(templates, '');
    expect(cards.find((c) => c.templateId === '').active).toBe(true);
    expect(cards.every((c) => c.templateId === '' || !c.active)).toBe(true);
  });

  it('marks the matching template card active and Custom inactive', () => {
    const cards = puzzleTemplateCardOptions(templates, 'cipher');
    expect(cards.find((c) => c.templateId === '').active).toBe(false);
    expect(cards.find((c) => c.templateId === 'cipher').active).toBe(true);
    expect(cards.find((c) => c.templateId === 'riddle').active).toBe(false);
  });

  it('tolerates a missing templates list', () => {
    expect(puzzleTemplateCardOptions(undefined)).toEqual([
      { templateId: '', label: 'Custom (blank)', description: 'Start from a blank puzzle.', propType: '', active: true },
    ]);
  });
});

describe('puzzlePropCardOptions (escape_room_feature_design.md section 5.4)', () => {
  it('offers a "no shape" card first, so a puzzle need not wear a prop at all', () => {
    const cards = puzzlePropCardOptions();
    expect(cards[0].propType).toBe('');
    expect(cards[0].active).toBe(true);
  });

  it('offers all five prop shapes after the "no shape" card', () => {
    const cards = puzzlePropCardOptions();
    expect(cards.slice(1).map((c) => c.propType)).toEqual([
      'cipher_box', 'digital_lock', 'combination_dial', 'riddle_tablet', 'clue_board',
    ]);
  });

  it('gives every shape a human label and a description of how it reads', () => {
    puzzlePropCardOptions().forEach((card) => {
      expect(card.label.length).toBeGreaterThan(0);
      expect(card.description.length).toBeGreaterThan(0);
    });
  });

  it('marks exactly the selected shape active', () => {
    const cards = puzzlePropCardOptions('digital_lock');
    expect(cards.filter((c) => c.active).map((c) => c.propType)).toEqual(['digital_lock']);
  });

  it('falls back to the "no shape" card when the selection is unknown', () => {
    const cards = puzzlePropCardOptions('not_a_prop');
    expect(cards.filter((c) => c.active).map((c) => c.propType)).toEqual(['']);
  });

  it('treats null and undefined selections as no shape', () => {
    expect(puzzlePropCardOptions(null)[0].active).toBe(true);
    expect(puzzlePropCardOptions(undefined)[0].active).toBe(true);
  });
});

describe('formatPuzzleAnalytics', () => {
  it('summarises attempts, success rate, and hint usage', () => {
    expect(formatPuzzleAnalytics({
      totalAttempts: 8, wrongAttempts: 6, distinctSolvers: 2, hintsRequested: 3, successRate: 0.25,
    })).toBe('8 attempts · 25% solved · 3 hints');
  });

  it('says so plainly when nobody has tried the puzzle yet', () => {
    expect(formatPuzzleAnalytics({
      totalAttempts: 0, wrongAttempts: 0, distinctSolvers: 0, hintsRequested: 0, successRate: null,
    })).toBe('No attempts yet');
  });

  it('rounds the success rate to a whole percent', () => {
    expect(formatPuzzleAnalytics({
      totalAttempts: 3, wrongAttempts: 2, distinctSolvers: 1, hintsRequested: 0, successRate: 1 / 3,
    })).toBe('3 attempts · 33% solved · 0 hints');
  });

  it('returns empty string for missing stats', () => {
    expect(formatPuzzleAnalytics(null)).toBe('');
  });
});

describe('puzzleDifficultySignal', () => {
  it('reports "unplayed" before anyone attempts it', () => {
    expect(puzzleDifficultySignal({ totalAttempts: 0, successRate: null })).toBe('unplayed');
  });

  it('reports "easy" when almost everyone gets it first try', () => {
    expect(puzzleDifficultySignal({ totalAttempts: 10, successRate: 0.9 })).toBe('easy');
  });

  it('reports "balanced" in the middle band', () => {
    expect(puzzleDifficultySignal({ totalAttempts: 10, successRate: 0.5 })).toBe('balanced');
  });

  it('reports "hard" when hardly anyone solves it', () => {
    expect(puzzleDifficultySignal({ totalAttempts: 20, successRate: 0.05 })).toBe('hard');
  });

  it('stays "unplayed" on a tiny sample, so one unlucky guess is not called "hard"', () => {
    expect(puzzleDifficultySignal({ totalAttempts: 2, successRate: 0 })).toBe('unplayed');
  });

  it('returns "unplayed" for missing stats', () => {
    expect(puzzleDifficultySignal(null)).toBe('unplayed');
  });
});

describe('validatePuzzleInput (design doc build_mode_ui_redesign_feature_design.md section 8.7, Gap 1)', () => {
  it('rejects a missing puzzle id', () => {
    expect(validatePuzzleInput({ puzzleId: '', prompt: 'p', answer: 'a' })).toEqual({
      valid: false, error: 'Puzzle ID, prompt, and answer are required.',
    });
  });

  it('rejects a missing answer', () => {
    expect(validatePuzzleInput({ puzzleId: 'puzzle-1', prompt: 'p', answer: '' })).toEqual({
      valid: false, error: 'Puzzle ID, prompt, and answer are required.',
    });
  });

  it('rejects a missing prompt when no template is selected', () => {
    expect(validatePuzzleInput({ puzzleId: 'puzzle-1', prompt: '', answer: 'a', templateId: undefined })).toEqual({
      valid: false, error: 'Puzzle ID, prompt, and answer are required.',
    });
  });

  it('accepts a missing prompt when a template is selected', () => {
    expect(validatePuzzleInput({ puzzleId: 'puzzle-1', prompt: '', answer: 'a', templateId: 'riddle-1' })).toEqual({
      valid: true, error: null,
    });
  });

  it('accepts a puzzle id, prompt, and answer with no template', () => {
    expect(validatePuzzleInput({ puzzleId: 'puzzle-1', prompt: 'p', answer: 'a' })).toEqual({
      valid: true, error: null,
    });
  });
});
