import { describe, it, expect } from 'vitest';
import {
  ROOM_STYLES,
  DEFAULT_ROOM_STYLE,
  isValidRoomStyle,
  resolveRoomStyle,
} from '../src/room-styles.js';

describe('ROOM_STYLES', () => {
  it('offers exactly 10 selectable empty-room styles', () => {
    expect(ROOM_STYLES).toHaveLength(10);
  });

  it('gives every style a unique id and label', () => {
    const ids = ROOM_STYLES.map((s) => s.id);
    const labels = ROOM_STYLES.map((s) => s.label);
    expect(new Set(ids).size).toBe(ROOM_STYLES.length);
    expect(new Set(labels).size).toBe(ROOM_STYLES.length);
  });

  it('gives every style the color fields the renderer needs', () => {
    for (const style of ROOM_STYLES) {
      expect(style.backdropTop).toMatch(/^#/);
      expect(style.backdropBottom).toMatch(/^#/);
      expect(style.wallTop).toMatch(/^#/);
      expect(style.wallBottom).toMatch(/^#/);
      expect(style.floorLight).toMatch(/^#/);
      expect(style.floorDark).toMatch(/^#/);
    }
  });

  it('includes the default style id among the presets', () => {
    expect(ROOM_STYLES.some((s) => s.id === DEFAULT_ROOM_STYLE)).toBe(true);
  });
});

describe('isValidRoomStyle', () => {
  it('returns true for every known style id', () => {
    for (const style of ROOM_STYLES) {
      expect(isValidRoomStyle(style.id)).toBe(true);
    }
  });

  it('returns false for an unknown style id', () => {
    expect(isValidRoomStyle('haunted-mansion')).toBe(false);
  });

  it('returns false for null/undefined/empty', () => {
    expect(isValidRoomStyle(null)).toBe(false);
    expect(isValidRoomStyle(undefined)).toBe(false);
    expect(isValidRoomStyle('')).toBe(false);
  });
});

describe('resolveRoomStyle', () => {
  it('returns the matching preset for a known style id', () => {
    const target = ROOM_STYLES[2];
    expect(resolveRoomStyle(target.id)).toEqual(target);
  });

  it('falls back to the default style for an unknown id', () => {
    const fallback = resolveRoomStyle('haunted-mansion');
    expect(fallback.id).toBe(DEFAULT_ROOM_STYLE);
  });

  it('falls back to the default style for null/undefined', () => {
    expect(resolveRoomStyle(null).id).toBe(DEFAULT_ROOM_STYLE);
    expect(resolveRoomStyle(undefined).id).toBe(DEFAULT_ROOM_STYLE);
  });
});
