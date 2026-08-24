/**
 * TDD tests for src/animation.js — walk phase logic.
 * Written BEFORE the implementation exists.
 */

import { describe, it, expect } from 'vitest';
import { advanceWalkPhase, WALK_PHASE_INCREMENT } from '../src/animation.js';

describe('WALK_PHASE_INCREMENT', () => {
  it('is a positive number less than 1', () => {
    expect(WALK_PHASE_INCREMENT).toBeGreaterThan(0);
    expect(WALK_PHASE_INCREMENT).toBeLessThan(1);
  });
});

describe('advanceWalkPhase', () => {
  describe('when the player has moved', () => {
    it('increments phase by the default increment', () => {
      const result = advanceWalkPhase(0, true);
      expect(result).toBeCloseTo(WALK_PHASE_INCREMENT, 10);
    });

    it('increments phase by a custom increment', () => {
      expect(advanceWalkPhase(0,    true, 0.1)).toBeCloseTo(0.1);
      expect(advanceWalkPhase(0.3,  true, 0.1)).toBeCloseTo(0.4);
      expect(advanceWalkPhase(0.55, true, 0.2)).toBeCloseTo(0.75);
    });

    it('wraps around at 1.0 (phase stays in [0, 1))', () => {
      expect(advanceWalkPhase(0.95, true, 0.1)).toBeCloseTo(0.05);
    });

    it('wraps cleanly when increment pushes exactly to 1', () => {
      // 0.9 + 0.1 = 1.0 → wraps to 0.0
      expect(advanceWalkPhase(0.9, true, 0.1)).toBeCloseTo(0.0);
    });

    it('wraps cleanly when increment overshoots 1 by a lot', () => {
      // 0.7 + 0.5 = 1.2 → wraps to 0.2
      expect(advanceWalkPhase(0.7, true, 0.5)).toBeCloseTo(0.2);
    });

    it('phase stays in [0, 1) after 1000 increments', () => {
      let phase = 0;
      for (let i = 0; i < 1000; i++) {
        phase = advanceWalkPhase(phase, true);
      }
      expect(phase).toBeGreaterThanOrEqual(0);
      expect(phase).toBeLessThan(1);
    });
  });

  describe('when the player has NOT moved', () => {
    it('returns the same phase unchanged (phase 0)', () => {
      expect(advanceWalkPhase(0, false)).toBe(0);
    });

    it('returns the same phase unchanged (arbitrary phase)', () => {
      expect(advanceWalkPhase(0.42, false)).toBe(0.42);
      expect(advanceWalkPhase(0.99, false)).toBe(0.99);
      expect(advanceWalkPhase(0.001, false)).toBe(0.001);
    });

    it('ignores the increment argument when not moved', () => {
      expect(advanceWalkPhase(0.5, false, 0.9)).toBe(0.5);
    });
  });

  describe('edge cases', () => {
    it('an increment of 0 never changes the phase', () => {
      expect(advanceWalkPhase(0.5, true, 0)).toBe(0.5);
    });

    it('is deterministic — same inputs produce same output', () => {
      const a = advanceWalkPhase(0.33, true, 0.07);
      const b = advanceWalkPhase(0.33, true, 0.07);
      expect(a).toBe(b);
    });

    it('handles phase starting at exactly 0', () => {
      expect(advanceWalkPhase(0, true, 0.5)).toBeCloseTo(0.5);
    });

    it('handles phase starting at near-maximum (0.9999)', () => {
      const result = advanceWalkPhase(0.9999, true, 0.0001);
      expect(result).toBeCloseTo(0);
      expect(result).toBeGreaterThanOrEqual(0);
      expect(result).toBeLessThan(1);
    });
  });
});
