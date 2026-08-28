import { describe, it, expect } from 'vitest';
import {
  escapeStatusLabel,
  formatCountdown,
  isLowTime,
  puzzleAttemptMessage,
  formatLeaderboardEntry,
  doorAttemptMessage,
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
