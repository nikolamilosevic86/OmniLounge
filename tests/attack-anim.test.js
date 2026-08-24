/**
 * TDD tests for src/attack-anim.js — arcade-style combat animations.
 *
 * ─── SVG rotate() sign convention (mathematically verified) ────────────────
 * Pivot is at the TOP of each limb (shoulder / hip); the limb hangs DOWN
 * at rest, i.e. its free end is at local offset (dx=0, dy=+L).
 *
 * SVG's rotate(θ) applies the matrix:
 *   x' = x·cosθ − y·sinθ
 *   y' = x·sinθ + y·cosθ
 *
 * For a point hanging straight down, (dx,dy) = (0, L):
 *   x' = −L·sinθ
 *
 * For θ > 0 (positive/"clockwise" in SVG), sinθ > 0 (for 0°<θ<180°), so
 * x' < 0 → the limb's end moves LEFT.
 * For θ < 0, x' > 0 → the limb's end moves RIGHT.
 *
 * ⇒ NEGATIVE angle → limb swings RIGHT (toward a right-side opponent)
 * ⇒ POSITIVE angle → limb swings LEFT  (toward a left-side opponent)
 *
 * A geometric anchor test below verifies this directly against the
 * rotation matrix so the convention can never silently regress again.
 *
 * ─── Animation curves ───────────────────────────────────────────────────────
 * Punch: 3-phase (wind-up → fast snap → retract) — snappy arcade jab
 * Kick:  2-phase (fast raise → slower lower) — heavy telegraphed kick
 * Block: linear ramp to a cross-guard — both arms swing INWARD (toward center)
 */

import { describe, it, expect } from 'vitest';
import {
  ATTACK_DURATIONS,
  computeAttackPhase,
  getPunchAngles,
  getKickAngles,
  getBlockAngles,
} from '../src/attack-anim.js';

// ─── geometric anchor: proves the sign convention is correct ────────────────

/** Rotate point (dx, dy) by angleDeg using the exact SVG rotate() matrix. */
function rotatePoint(dx, dy, angleDeg) {
  const a = (angleDeg * Math.PI) / 180;
  return {
    x: dx * Math.cos(a) - dy * Math.sin(a),
    y: dx * Math.sin(a) + dy * Math.cos(a),
  };
}

describe('geometric anchor — SVG rotation matrix sanity check', () => {
  it('a NEGATIVE angle swings a hanging limb (dx=0,dy=L) to the RIGHT (x>0)', () => {
    const { x } = rotatePoint(0, 100, -45);
    expect(x).toBeGreaterThan(0);
  });
  it('a POSITIVE angle swings a hanging limb to the LEFT (x<0)', () => {
    const { x } = rotatePoint(0, 100, 45);
    expect(x).toBeLessThan(0);
  });
});

describe('getPunchAngles output obeys the geometric convention (facingRight)', () => {
  it('rightArmAngle at peak, when applied to a hanging arm, actually points RIGHT', () => {
    const { rightArmAngle } = getPunchAngles(0.46, true); // peak
    const { x } = rotatePoint(0, 100, rightArmAngle);
    expect(x).toBeGreaterThan(0);
  });
});

describe('getPunchAngles output obeys the geometric convention (facingLeft)', () => {
  it('leftArmAngle at peak, when applied to a hanging arm, actually points LEFT', () => {
    const { leftArmAngle } = getPunchAngles(0.46, false); // peak
    const { x } = rotatePoint(0, 100, leftArmAngle);
    expect(x).toBeLessThan(0);
  });
});

describe('getKickAngles output obeys the geometric convention (facingRight)', () => {
  it('rightLegAngle at peak actually points RIGHT', () => {
    const { rightLegAngle } = getKickAngles(0.42, true); // peak
    const { x } = rotatePoint(0, 100, rightLegAngle);
    expect(x).toBeGreaterThan(0);
  });
});

describe('getKickAngles output obeys the geometric convention (facingLeft)', () => {
  it('leftLegAngle at peak actually points LEFT', () => {
    const { leftLegAngle } = getKickAngles(0.42, false); // peak
    const { x } = rotatePoint(0, 100, leftLegAngle);
    expect(x).toBeLessThan(0);
  });
});

describe('getBlockAngles output obeys the geometric convention (cross guard)', () => {
  it('left arm at full guard swings toward the CENTER (right, x>0 relative to left shoulder)', () => {
    const { leftArmAngle } = getBlockAngles(1);
    const { x } = rotatePoint(0, 100, leftArmAngle);
    expect(x).toBeGreaterThan(0); // moves right = inward, since left arm starts on the left
  });
  it('right arm at full guard swings toward the CENTER (left, x<0 relative to right shoulder)', () => {
    const { rightArmAngle } = getBlockAngles(1);
    const { x } = rotatePoint(0, 100, rightArmAngle);
    expect(x).toBeLessThan(0); // moves left = inward, since right arm starts on the right
  });
});

// ─── ATTACK_DURATIONS ────────────────────────────────────────────────────────

describe('ATTACK_DURATIONS', () => {
  it('defines punch and kick', () => {
    expect(ATTACK_DURATIONS.punch).toBeGreaterThan(0);
    expect(ATTACK_DURATIONS.kick).toBeGreaterThan(0);
  });
  it('kick is slower than punch (more weight)', () => {
    expect(ATTACK_DURATIONS.kick).toBeGreaterThan(ATTACK_DURATIONS.punch);
  });
  it('punch completes in under 600 ms (snappy arcade feel)', () => {
    expect(ATTACK_DURATIONS.punch).toBeLessThan(600);
  });
  it('kick completes in under 800 ms', () => {
    expect(ATTACK_DURATIONS.kick).toBeLessThan(800);
  });
});

// ─── computeAttackPhase ──────────────────────────────────────────────────────

describe('computeAttackPhase', () => {
  it('0 at start', ()  => expect(computeAttackPhase(1000, 1000, 500)).toBe(0));
  it('0.5 at midpoint', () => expect(computeAttackPhase(1000, 1250, 500)).toBe(0.5));
  it('1 at end',  () => expect(computeAttackPhase(1000, 1500, 500)).toBe(1));
  it('clamps to 1 past end',  () => expect(computeAttackPhase(1000, 9999, 500)).toBe(1));
  it('clamps to 0 before start', () => expect(computeAttackPhase(1000, 500, 500)).toBe(0));
  it('is deterministic', () => expect(computeAttackPhase(0,77,300)).toBe(computeAttackPhase(0,77,300)));
});

// ─── getPunchAngles — shape ──────────────────────────────────────────────────

describe('getPunchAngles — shape', () => {
  it('all angles 0 at phase=0', () => {
    const r = getPunchAngles(0);
    expect(r.leftArmAngle).toBeCloseTo(0,1);
    expect(r.rightArmAngle).toBeCloseTo(0,1);
    expect(r.leftLegAngle).toBeCloseTo(0,1);
    expect(r.rightLegAngle).toBeCloseTo(0,1);
  });
  it('all angles return to 0 at phase=1', () => {
    const r = getPunchAngles(1);
    expect(r.leftArmAngle).toBeCloseTo(0,1);
    expect(r.rightArmAngle).toBeCloseTo(0,1);
  });
  it('legs never move during a punch', () => {
    [0, 0.1, 0.25, 0.5, 0.75, 1].forEach(p => {
      const { leftLegAngle, rightLegAngle } = getPunchAngles(p);
      expect(leftLegAngle).toBeCloseTo(0,1);
      expect(rightLegAngle).toBeCloseTo(0,1);
    });
  });
  it('returns all four angle keys', () => {
    const r = getPunchAngles(0.5);
    ['leftArmAngle','rightArmAngle','leftLegAngle','rightLegAngle'].forEach(k =>
      expect(r).toHaveProperty(k));
  });
});

describe('getPunchAngles — facingRight (opponent to the RIGHT)', () => {
  it('wind-up: at early phase (~10%), strike arm (right) pulls back — magnitude nonzero', () => {
    const { rightArmAngle } = getPunchAngles(0.08, true);
    expect(rightArmAngle).not.toBeCloseTo(0, 1);
  });
  it('wind-up direction: right arm briefly points LEFT (away from target) before the snap', () => {
    const { rightArmAngle } = getPunchAngles(0.08, true);
    const { x } = rotatePoint(0, 100, rightArmAngle);
    expect(x).toBeLessThan(0); // pulled back/left before snapping right
  });
  it('peak: strike arm (right) swings strongly toward the opponent', () => {
    const angles = [0.4,0.45,0.5,0.55].map(p => getPunchAngles(p, true).rightArmAngle);
    const extreme = angles.reduce((a,b) => Math.abs(a) > Math.abs(b) ? a : b);
    expect(Math.abs(extreme)).toBeGreaterThan(82);
    const { x } = rotatePoint(0, 100, extreme);
    expect(x).toBeGreaterThan(0); // points right, toward opponent
  });
  it('non-strike arm (left) counter-swings away from opponent at peak', () => {
    const { leftArmAngle } = getPunchAngles(0.5, true);
    const { x } = rotatePoint(0, 100, leftArmAngle);
    expect(x).toBeLessThan(0); // swings left = away from right-side opponent
  });
  it('symmetric retract: |angle at 0.75| < |angle at 0.5|', () => {
    expect(Math.abs(getPunchAngles(0.75, true).rightArmAngle))
      .toBeLessThan(Math.abs(getPunchAngles(0.5, true).rightArmAngle));
  });
});

describe('getPunchAngles — facingLeft (opponent to the LEFT)', () => {
  it('wind-up direction: left arm briefly points RIGHT (away from target) before the snap', () => {
    const { leftArmAngle } = getPunchAngles(0.08, false);
    const { x } = rotatePoint(0, 100, leftArmAngle);
    expect(x).toBeGreaterThan(0);
  });
  it('peak: strike arm (left) swings strongly toward the opponent', () => {
    const angles = [0.4,0.45,0.5,0.55].map(p => getPunchAngles(p, false).leftArmAngle);
    const extreme = angles.reduce((a,b) => Math.abs(a) > Math.abs(b) ? a : b);
    expect(Math.abs(extreme)).toBeGreaterThan(82);
    const { x } = rotatePoint(0, 100, extreme);
    expect(x).toBeLessThan(0); // points left, toward opponent
  });
  it('non-strike arm (right) counter-swings away from opponent', () => {
    const { rightArmAngle } = getPunchAngles(0.5, false);
    const { x } = rotatePoint(0, 100, rightArmAngle);
    expect(x).toBeGreaterThan(0);
  });
  it('mirrors facingRight in magnitude at every phase', () => {
    [0, 0.25, 0.5, 0.75, 1].forEach(p => {
      const l = getPunchAngles(p, false).leftArmAngle;
      const r = getPunchAngles(p, true).rightArmAngle;
      expect(Math.abs(l)).toBeCloseTo(Math.abs(r), 0);
    });
  });
});

// ─── getKickAngles — shape ───────────────────────────────────────────────────

describe('getKickAngles — shape', () => {
  it('all angles 0 at phase=0', () => {
    const r = getKickAngles(0);
    ['leftArmAngle','rightArmAngle','leftLegAngle','rightLegAngle'].forEach(k =>
      expect(r[k]).toBeCloseTo(0,1));
  });
  it('all leg angles return to 0 at phase=1', () => {
    const r = getKickAngles(1);
    expect(r.leftLegAngle).toBeCloseTo(0,1);
    expect(r.rightLegAngle).toBeCloseTo(0,1);
  });
  it('returns all four angle keys', () => {
    const r = getKickAngles(0.5);
    ['leftArmAngle','rightArmAngle','leftLegAngle','rightLegAngle'].forEach(k =>
      expect(r).toHaveProperty(k));
  });
});

describe('getKickAngles — facingRight', () => {
  it('kick leg (right) swings strongly toward the opponent (right) at peak', () => {
    const angles = [0.35,0.4,0.45,0.5].map(p => getKickAngles(p, true).rightLegAngle);
    const extreme = angles.reduce((a,b) => Math.abs(a) > Math.abs(b) ? a : b);
    expect(Math.abs(extreme)).toBeGreaterThan(85);
    const { x } = rotatePoint(0, 100, extreme);
    expect(x).toBeGreaterThan(0);
  });
  it('kick leg does not clip: |peak angle| ≤ 95°', () => {
    const angles = [0.35,0.4,0.45,0.5].map(p => Math.abs(getKickAngles(p, true).rightLegAngle));
    expect(Math.max(...angles)).toBeLessThanOrEqual(95);
  });
  it('left leg (support) stays small throughout', () => {
    [0.1,0.25,0.4,0.5,0.7,0.9].forEach(p =>
      expect(Math.abs(getKickAngles(p, true).leftLegAngle)).toBeLessThan(20));
  });
  it('arms splay for balance at peak: both non-zero, both under 40°', () => {
    const { leftArmAngle, rightArmAngle } = getKickAngles(0.4, true);
    expect(Math.abs(leftArmAngle)).toBeGreaterThan(5);
    expect(Math.abs(rightArmAngle)).toBeGreaterThan(5);
    expect(Math.abs(leftArmAngle)).toBeLessThan(40);
    expect(Math.abs(rightArmAngle)).toBeLessThan(40);
  });
  it('kick raises fast: |angle| at phase=0.35 > 50°', () => {
    expect(Math.abs(getKickAngles(0.35, true).rightLegAngle)).toBeGreaterThan(50);
  });
  it('kick lowers after peak: |angle at 0.9| < |angle at 0.42|', () => {
    expect(Math.abs(getKickAngles(0.9, true).rightLegAngle))
      .toBeLessThan(Math.abs(getKickAngles(0.42, true).rightLegAngle));
  });
});

describe('getKickAngles — facingLeft', () => {
  it('kick leg (left) swings strongly toward the opponent (left) at peak', () => {
    const angles = [0.35,0.4,0.45,0.5].map(p => getKickAngles(p, false).leftLegAngle);
    const extreme = angles.reduce((a,b) => Math.abs(a) > Math.abs(b) ? a : b);
    expect(Math.abs(extreme)).toBeGreaterThan(85);
    const { x } = rotatePoint(0, 100, extreme);
    expect(x).toBeLessThan(0);
  });
  it('right leg (support) stays small throughout', () => {
    [0.1,0.25,0.4,0.5,0.7,0.9].forEach(p =>
      expect(Math.abs(getKickAngles(p, false).rightLegAngle)).toBeLessThan(20));
  });
  it('mirrors facingRight in magnitude at every phase', () => {
    [0.1, 0.3, 0.5, 0.7, 0.9].forEach(p => {
      const l = getKickAngles(p, false).leftLegAngle;
      const r = getKickAngles(p, true).rightLegAngle;
      expect(Math.abs(l)).toBeCloseTo(Math.abs(r), 0);
    });
  });
});

// ─── getBlockAngles — cross guard ────────────────────────────────────────────

describe('getBlockAngles — cross guard', () => {
  it('all angles 0 at phase=0 (neutral stance)', () => {
    const r = getBlockAngles(0);
    expect(r.leftArmAngle).toBeCloseTo(0,1);
    expect(r.rightArmAngle).toBeCloseTo(0,1);
  });
  it('guard is strong: |arm angles| ≥ 72° at phase=1', () => {
    const r = getBlockAngles(1);
    expect(Math.abs(r.leftArmAngle)).toBeGreaterThanOrEqual(72);
    expect(Math.abs(r.rightArmAngle)).toBeGreaterThanOrEqual(72);
  });
  it('guard does not over-extend past 90° (no clipping)', () => {
    const r = getBlockAngles(1);
    expect(Math.abs(r.leftArmAngle)).toBeLessThanOrEqual(90);
    expect(Math.abs(r.rightArmAngle)).toBeLessThanOrEqual(90);
  });
  it('left and right arm angles have OPPOSITE signs (true cross guard, not a mirrored open)', () => {
    const r = getBlockAngles(1);
    expect(Math.sign(r.leftArmAngle)).not.toBe(Math.sign(r.rightArmAngle));
  });
  it('arms are symmetric in magnitude at all phases', () => {
    [0, 0.25, 0.5, 0.75, 1].forEach(p => {
      const r = getBlockAngles(p);
      expect(Math.abs(r.leftArmAngle)).toBeCloseTo(Math.abs(r.rightArmAngle), 1);
    });
  });
  it('guard interpolates smoothly: angle at 0.5 ≈ half of phase=1', () => {
    const half = getBlockAngles(0.5);
    const full = getBlockAngles(1);
    expect(half.leftArmAngle).toBeCloseTo(full.leftArmAngle * 0.5, 0);
  });
  it('guard magnitude is monotonically increasing with phase', () => {
    const a = Math.abs(getBlockAngles(0.25).leftArmAngle);
    const b = Math.abs(getBlockAngles(0.5).leftArmAngle);
    const c = Math.abs(getBlockAngles(0.75).leftArmAngle);
    const d = Math.abs(getBlockAngles(1.0).leftArmAngle);
    expect(a).toBeLessThan(b);
    expect(b).toBeLessThan(c);
    expect(c).toBeLessThanOrEqual(d);
  });
  it('clamps at phase > 1', () => {
    expect(getBlockAngles(2).leftArmAngle).toBeCloseTo(getBlockAngles(1).leftArmAngle, 1);
  });
  it('clamps at phase < 0', () => {
    expect(getBlockAngles(-0.5).leftArmAngle).toBeCloseTo(0, 1);
  });
});

// ─── full-cycle integration ──────────────────────────────────────────────────

describe('full punch cycle (facingRight)', () => {
  it('right arm: starts 0, dips positive (wind-up/left), snaps negative (peak/right), returns 0', () => {
    const samples = Array.from({length:20}, (_,i) => getPunchAngles(i/19, true).rightArmAngle);
    expect(samples[0]).toBeCloseTo(0,1);
    expect(samples[19]).toBeCloseTo(0,1);
    const peakIdx = samples.reduce((best,val,idx) => Math.abs(val) > Math.abs(samples[best]) ? idx : best, 0);
    expect(Math.abs(samples[peakIdx])).toBeGreaterThan(82);
    expect(samples[peakIdx]).toBeLessThan(0); // peak points right (negative angle)
    expect(peakIdx).toBeGreaterThanOrEqual(7);
    expect(peakIdx).toBeLessThanOrEqual(11);
  });
});

describe('full kick cycle (facingRight)', () => {
  it('right leg: starts 0, peaks in magnitude >85° toward the right, returns to 0', () => {
    const samples = Array.from({length:20}, (_,i) => getKickAngles(i/19, true).rightLegAngle);
    expect(samples[0]).toBeCloseTo(0,1);
    expect(samples[19]).toBeCloseTo(0,1);
    const peakIdx = samples.reduce((best,val,idx) => Math.abs(val) > Math.abs(samples[best]) ? idx : best, 0);
    expect(Math.abs(samples[peakIdx])).toBeGreaterThan(85);
    const { x } = rotatePoint(0, 100, samples[peakIdx]);
    expect(x).toBeGreaterThan(0);
  });
});
