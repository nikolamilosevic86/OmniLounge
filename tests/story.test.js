import { describe, it, expect } from 'vitest';
import {
  CHARACTER_ROLES,
  isValidCharacterRole,
  formatModeLabel,
  parseChoicesInput,
  resolveCharacterMode,
} from '../src/story.js';

describe('CHARACTER_ROLES', () => {
  it('includes the five design-doc roles', () => {
    expect(CHARACTER_ROLES).toEqual(['guide', 'quiz_master', 'narrator', 'historical_persona', 'mentor']);
  });
});

describe('isValidCharacterRole', () => {
  it('returns true for a known role', () => {
    expect(isValidCharacterRole('guide')).toBe(true);
  });

  it('returns false for an unknown role', () => {
    expect(isValidCharacterRole('wizard')).toBe(false);
  });
});

describe('formatModeLabel', () => {
  it('formats predefined mode', () => {
    expect(formatModeLabel('predefined')).toBe('Predefined Mode');
  });

  it('formats generative mode', () => {
    expect(formatModeLabel('generative')).toBe('Generative Mode');
  });

  it('formats rate-limited mode', () => {
    expect(formatModeLabel('rate_limited')).toBe('Please Wait');
  });

  it('falls back gracefully for an unknown mode', () => {
    expect(formatModeLabel(undefined)).toBe('Predefined Mode');
  });
});

describe('parseChoicesInput', () => {
  it('parses one "text | nextNodeId" pair per line', () => {
    const input = 'Continue | node-2\nGo back | node-1';
    expect(parseChoicesInput(input)).toEqual([
      { text: 'Continue', nextNodeId: 'node-2' },
      { text: 'Go back', nextNodeId: 'node-1' },
    ]);
  });

  it('treats a line with no pipe as an end-of-story choice (no nextNodeId)', () => {
    expect(parseChoicesInput('The end')).toEqual([{ text: 'The end', nextNodeId: null }]);
  });

  it('ignores blank lines', () => {
    expect(parseChoicesInput('Continue | node-2\n\n')).toEqual([{ text: 'Continue', nextNodeId: 'node-2' }]);
  });

  it('returns an empty array for empty or null input', () => {
    expect(parseChoicesInput('')).toEqual([]);
    expect(parseChoicesInput(null)).toEqual([]);
  });
});

describe('resolveCharacterMode', () => {
  it('returns generative when the character has generative mode enabled', () => {
    expect(resolveCharacterMode({ generativeEnabled: true })).toBe('generative');
  });

  it('returns predefined when the character has generative mode disabled', () => {
    expect(resolveCharacterMode({ generativeEnabled: false })).toBe('predefined');
  });

  it('returns predefined for a null or undefined character', () => {
    expect(resolveCharacterMode(null)).toBe('predefined');
    expect(resolveCharacterMode(undefined)).toBe('predefined');
  });
});
