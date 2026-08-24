/**
 * TDD tests for src/combat.js — written BEFORE implementation (RED phase).
 */
import { describe, it, expect } from 'vitest';
import {
  ATTACK_TYPES,
  MAX_STAMINA,
  BLOCK_REDUCTION,
  calculateDamage,
  canAttack,
  isInRange,
  applyHit,
  regenStamina,
  isStunned,
} from '../src/combat.js';

describe('ATTACK_TYPES', () => {
  it('has punch and kick entries', () => {
    expect(ATTACK_TYPES.punch).toBeDefined();
    expect(ATTACK_TYPES.kick).toBeDefined();
  });
  it('punch has lower damage than kick', () => {
    expect(ATTACK_TYPES.punch.damage).toBeLessThan(ATTACK_TYPES.kick.damage);
  });
  it('punch has shorter cooldown than kick', () => {
    expect(ATTACK_TYPES.punch.cooldownMs).toBeLessThan(ATTACK_TYPES.kick.cooldownMs);
  });
  it('punch has lower stamina cost than kick', () => {
    expect(ATTACK_TYPES.punch.staminaCost).toBeLessThan(ATTACK_TYPES.kick.staminaCost);
  });
});

describe('calculateDamage', () => {
  it('returns full damage when not blocked', () => {
    expect(calculateDamage('punch', false)).toBe(ATTACK_TYPES.punch.damage);
    expect(calculateDamage('kick',  false)).toBe(ATTACK_TYPES.kick.damage);
  });
  it('returns reduced damage when blocked', () => {
    expect(calculateDamage('punch', true)).toBeLessThan(ATTACK_TYPES.punch.damage);
    expect(calculateDamage('punch', true)).toBeGreaterThan(0);
  });
  it('applies BLOCK_REDUCTION correctly', () => {
    const full    = ATTACK_TYPES.punch.damage;
    const blocked = calculateDamage('punch', true);
    expect(blocked).toBe(Math.round(full * (1 - BLOCK_REDUCTION)));
  });
  it('returns 0 for unknown attack type', () => {
    expect(calculateDamage('headbutt', false)).toBe(0);
  });
});

describe('canAttack', () => {
  it('allows attack when stamina sufficient and cooldown elapsed', () => {
    expect(canAttack(100, 0, 2000, 'punch')).toBe(true);
  });
  it('blocks when stamina too low', () => {
    expect(canAttack(4, 0, 2000, 'punch')).toBe(false); // costs 8
  });
  it('blocks when cooldown not elapsed', () => {
    expect(canAttack(100, 1600, 2000, 'punch')).toBe(false); // 400ms < 600ms cooldown
  });
  it('allows attack exactly when cooldown elapsed', () => {
    expect(canAttack(100, 0, 600, 'punch')).toBe(true); // exactly at limit
  });
  it('returns false for unknown attack type', () => {
    expect(canAttack(100, 0, 2000, 'slap')).toBe(false);
  });
});

describe('isInRange', () => {
  it('returns true when within range', () => {
    expect(isInRange({ x: 100, y: 100 }, { x: 160, y: 100 }, 'punch')).toBe(true); // 60px
  });
  it('returns false when out of range', () => {
    expect(isInRange({ x: 100, y: 100 }, { x: 300, y: 100 }, 'punch')).toBe(false); // 200px
  });
  it('returns true exactly at range boundary', () => {
    const r = ATTACK_TYPES.punch.range;
    expect(isInRange({ x: 0, y: 0 }, { x: r, y: 0 }, 'punch')).toBe(true);
  });
  it('returns false for unknown attack type', () => {
    expect(isInRange({ x: 0, y: 0 }, { x: 5, y: 0 }, 'headbutt')).toBe(false);
  });
});

describe('applyHit', () => {
  it('reduces stamina by damage amount', () => {
    expect(applyHit(100, 12)).toBe(88);
  });
  it('clamps stamina to 0', () => {
    expect(applyHit(10, 20)).toBe(0);
  });
  it('never returns negative stamina', () => {
    expect(applyHit(0, 100)).toBe(0);
  });
});

describe('regenStamina', () => {
  it('increases stamina over time', () => {
    expect(regenStamina(50, 1000)).toBeGreaterThan(50);
  });
  it('clamps to MAX_STAMINA', () => {
    expect(regenStamina(98, 5000)).toBe(MAX_STAMINA);
  });
  it('no change with delta 0', () => {
    expect(regenStamina(60, 0)).toBe(60);
  });
  it('increases by ~18 per second', () => {
    const result = regenStamina(0, 1000);
    expect(result).toBeCloseTo(18, 0);
  });
});

describe('isStunned', () => {
  it('returns true when stamina is 0', () => {
    expect(isStunned(0)).toBe(true);
  });
  it('returns false when stamina above 0', () => {
    expect(isStunned(1)).toBe(false);
    expect(isStunned(100)).toBe(false);
  });
});
