import { describe, it, expect } from 'vitest';
import { FOCUSABLE_SELECTOR, getNextFocusIndex, isEscapeKey } from '../src/focus-trap.js';

describe('FOCUSABLE_SELECTOR', () => {
  it('targets common interactive elements', () => {
    expect(FOCUSABLE_SELECTOR).toContain('button');
    expect(FOCUSABLE_SELECTOR).toContain('input');
    expect(FOCUSABLE_SELECTOR).toContain('a[href]');
    expect(FOCUSABLE_SELECTOR).toContain('select');
    expect(FOCUSABLE_SELECTOR).toContain('textarea');
  });
});

describe('isEscapeKey', () => {
  it('returns true for Escape', () => {
    expect(isEscapeKey('Escape')).toBe(true);
  });

  it('returns false for other keys', () => {
    expect(isEscapeKey('Enter')).toBe(false);
    expect(isEscapeKey('Tab')).toBe(false);
    expect(isEscapeKey(undefined)).toBe(false);
  });
});

describe('getNextFocusIndex', () => {
  it('moves forward one step without shift key', () => {
    expect(getNextFocusIndex(0, 3, { shiftKey: false })).toBe(1);
    expect(getNextFocusIndex(1, 3, { shiftKey: false })).toBe(2);
  });

  it('wraps forward from the last element back to the first', () => {
    expect(getNextFocusIndex(2, 3, { shiftKey: false })).toBe(0);
  });

  it('moves backward one step with shift key', () => {
    expect(getNextFocusIndex(2, 3, { shiftKey: true })).toBe(1);
  });

  it('wraps backward from the first element to the last', () => {
    expect(getNextFocusIndex(0, 3, { shiftKey: true })).toBe(2);
  });

  it('returns 0 when there are no focusable elements', () => {
    expect(getNextFocusIndex(0, 0, { shiftKey: false })).toBe(0);
    expect(getNextFocusIndex(-1, 0, { shiftKey: true })).toBe(0);
  });

  it('treats an unknown current index as not found and starts at 0 going forward', () => {
    expect(getNextFocusIndex(-1, 3, { shiftKey: false })).toBe(0);
  });
});
