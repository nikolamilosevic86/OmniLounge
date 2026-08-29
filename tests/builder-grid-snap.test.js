import { describe, it, expect } from 'vitest';
import { snapToGrid, snapPoint, DEFAULT_GRID_SIZE } from '../src/builder-grid-snap.js';

describe('snapToGrid (design doc build_mode_ui_redesign_feature_design.md section 12)', () => {
  it('rounds a value to the nearest grid line using the default 20px grid', () => {
    expect(snapToGrid(0)).toBe(0);
    expect(snapToGrid(9)).toBe(0);
    expect(snapToGrid(11)).toBe(20);
    expect(snapToGrid(20)).toBe(20);
  });

  it('rounds down exactly at the midpoint', () => {
    expect(snapToGrid(10)).toBe(20);
  });

  it('supports a custom grid size', () => {
    expect(snapToGrid(24, 10)).toBe(20);
    expect(snapToGrid(27, 10)).toBe(30);
  });

  it('handles negative values symmetrically', () => {
    expect(snapToGrid(-9)).toBe(0);
    expect(snapToGrid(-11)).toBe(-20);
  });

  it('exposes the default grid size as a constant', () => {
    expect(DEFAULT_GRID_SIZE).toBe(20);
  });
});

describe('snapPoint', () => {
  it('returns the point unchanged when snapping is disabled', () => {
    expect(snapPoint({ x: 13, y: 27 }, false)).toEqual({ x: 13, y: 27 });
  });

  it('snaps both x and y to the grid when enabled', () => {
    expect(snapPoint({ x: 13, y: 27 }, true)).toEqual({ x: 20, y: 20 });
  });

  it('supports a custom grid size when enabled', () => {
    expect(snapPoint({ x: 13, y: 27 }, true, 10)).toEqual({ x: 10, y: 30 });
  });
});
