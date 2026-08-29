import { describe, it, expect } from 'vitest';
import { computeTableLayout, tileTransitionDirection, renderObjectThumbnail } from '../client/js/room-renderer.js';

describe('computeTableLayout', () => {
  it('positions the legs flush against the underside of the tabletop with no gap', () => {
    const { topCenterY, topH, legTopY } = computeTableLayout(100, 80);
    const tabletopBottomEdge = topCenterY + topH / 2;

    expect(legTopY).toBeCloseTo(tabletopBottomEdge);
  });

  it('extends the legs all the way down to the sprite bottom edge', () => {
    const h = 80;
    const { legTopY, legH } = computeTableLayout(100, h);

    expect(legTopY + legH).toBeCloseTo(h / 2);
  });

  it('scales proportionally with different table sizes', () => {
    const small = computeTableLayout(60, 40);
    const large = computeTableLayout(120, 80);

    expect(small.legH).toBeGreaterThan(0);
    expect(large.legH).toBeGreaterThan(small.legH);
  });
});

describe('tileTransitionDirection', () => {
  it('returns "top" when moving to the tile above (decreasing y)', () => {
    expect(tileTransitionDirection({ x: 0, y: 0 }, { x: 0, y: -1 })).toBe('top');
  });

  it('returns "bottom" when moving to the tile below (increasing y)', () => {
    expect(tileTransitionDirection({ x: 0, y: 0 }, { x: 0, y: 1 })).toBe('bottom');
  });

  it('returns "left" when moving to the tile to the left (decreasing x)', () => {
    expect(tileTransitionDirection({ x: 0, y: 0 }, { x: -1, y: 0 })).toBe('left');
  });

  it('returns "right" when moving to the tile to the right (increasing x)', () => {
    expect(tileTransitionDirection({ x: 0, y: 0 }, { x: 1, y: 0 })).toBe('right');
  });

  it('returns null when the tile has not changed', () => {
    expect(tileTransitionDirection({ x: 2, y: -1 }, { x: 2, y: -1 })).toBeNull();
  });

  it('returns null for non-adjacent or diagonal tile jumps', () => {
    expect(tileTransitionDirection({ x: 0, y: 0 }, { x: 1, y: 1 })).toBeNull();
    expect(tileTransitionDirection({ x: 0, y: 0 }, { x: 2, y: 0 })).toBeNull();
  });

  it('returns null when either tile is missing', () => {
    expect(tileTransitionDirection(null, { x: 0, y: 0 })).toBeNull();
    expect(tileTransitionDirection({ x: 0, y: 0 }, undefined)).toBeNull();
  });
});

describe('renderObjectThumbnail (design doc build_mode_ui_redesign_feature_design.md section 9)', () => {
  it('returns null outside a DOM environment (no document to create a canvas with)', () => {
    expect(renderObjectThumbnail({ objectType: 'chair', color: 'navy' })).toBeNull();
  });
});
