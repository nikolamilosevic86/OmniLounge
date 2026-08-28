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
