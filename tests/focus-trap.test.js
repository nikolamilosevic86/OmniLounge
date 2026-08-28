import { describe, it, expect } from 'vitest';
import { FOCUSABLE_SELECTOR, getNextFocusIndex, isEscapeKey, isTextEntryElement } from '../src/focus-trap.js';

describe('isTextEntryElement', () => {
  it('treats text-like inputs as typing so arrow keys edit the caret', () => {
    for (const type of ['text', 'search', 'email', 'password', 'number', 'url', 'tel']) {
      expect(isTextEntryElement({ tagName: 'INPUT', type })).toBe(true);
    }
  });

  it('treats a textarea and contenteditable regions as typing', () => {
    expect(isTextEntryElement({ tagName: 'TEXTAREA' })).toBe(true);
    expect(isTextEntryElement({ tagName: 'DIV', isContentEditable: true })).toBe(true);
  });

  it('defaults a typeless input to text', () => {
    expect(isTextEntryElement({ tagName: 'INPUT' })).toBe(true);
  });

  // Regression: the build panel's Object Type/Size/Color dropdowns keep DOM
  // focus after use, so counting <select> as "typing" swallowed every arrow
  // key and made the avatar look permanently stuck after placing an object.
  it('does NOT treat a select dropdown as typing', () => {
    expect(isTextEntryElement({ tagName: 'SELECT' })).toBe(false);
  });

  it('does NOT treat checkboxes, radios or buttons as typing', () => {
    expect(isTextEntryElement({ tagName: 'INPUT', type: 'checkbox' })).toBe(false);
    expect(isTextEntryElement({ tagName: 'INPUT', type: 'radio' })).toBe(false);
    expect(isTextEntryElement({ tagName: 'INPUT', type: 'range' })).toBe(false);
    expect(isTextEntryElement({ tagName: 'BUTTON' })).toBe(false);
  });

  it('is case-insensitive about tag and type', () => {
    expect(isTextEntryElement({ tagName: 'input', type: 'TEXT' })).toBe(true);
    expect(isTextEntryElement({ tagName: 'select' })).toBe(false);
  });

  it('returns false for null/undefined or a plain container', () => {
    expect(isTextEntryElement(null)).toBe(false);
    expect(isTextEntryElement(undefined)).toBe(false);
    expect(isTextEntryElement({ tagName: 'BODY' })).toBe(false);
  });
});

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
