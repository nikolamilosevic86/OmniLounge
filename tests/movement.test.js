import { describe, it, expect } from 'vitest';
import {
  createPosition,
  moveToward,
  clampPosition,
  isWithinBounds,
  calculateDistance,
  ROOM_BOUNDS,
} from '../src/movement.js';

describe('Movement', () => {
  describe('createPosition', () => {
    it('creates a position with default center', () => {
      const pos = createPosition();
      expect(pos.x).toBe(ROOM_BOUNDS.width / 2);
      expect(pos.y).toBe(ROOM_BOUNDS.height / 2);
    });

    it('creates a position with custom coordinates', () => {
      const pos = createPosition(100, 200);
      expect(pos.x).toBe(100);
      expect(pos.y).toBe(200);
    });
  });

  describe('moveToward', () => {
    it('moves toward target by step amount', () => {
      const current = createPosition(0, 0);
      const target = { x: 100, y: 0 };
      const result = moveToward(current, target, 10);

      expect(result.x).toBe(10);
      expect(result.y).toBe(0);
    });

    it('snaps to target when within step distance', () => {
      const current = createPosition(95, 0);
      const target = { x: 100, y: 0 };
      const result = moveToward(current, target, 10);

      expect(result.x).toBe(100);
      expect(result.y).toBe(0);
    });

    it('moves diagonally toward target', () => {
      const current = createPosition(0, 0);
      const target = { x: 30, y: 40 };
      const result = moveToward(current, target, 5);

      const dist = calculateDistance(result, target);
      expect(dist).toBeLessThan(calculateDistance(current, target));
    });
  });

  describe('clampPosition', () => {
    it('keeps position within room bounds', () => {
      const pos = createPosition(-10, 9999);
      const clamped = clampPosition(pos);

      expect(clamped.x).toBeGreaterThanOrEqual(ROOM_BOUNDS.minX);
      expect(clamped.x).toBeLessThanOrEqual(ROOM_BOUNDS.maxX);
      expect(clamped.y).toBeGreaterThanOrEqual(ROOM_BOUNDS.minY);
      expect(clamped.y).toBeLessThanOrEqual(ROOM_BOUNDS.maxY);
    });
  });

  describe('isWithinBounds', () => {
    it('returns true for position inside room', () => {
      const pos = createPosition(400, 300);
      expect(isWithinBounds(pos)).toBe(true);
    });

    it('returns false for position outside room', () => {
      const pos = createPosition(-1, 300);
      expect(isWithinBounds(pos)).toBe(false);
    });
  });

  describe('calculateDistance', () => {
    it('calculates euclidean distance', () => {
      const a = createPosition(0, 0);
      const b = createPosition(3, 4);
      expect(calculateDistance(a, b)).toBe(5);
    });
  });
});
