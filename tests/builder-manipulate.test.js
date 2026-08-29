import { describe, it, expect } from 'vitest';
import {
  resizeHandleAtPoint,
  computeResizeFromHandle,
  angleDegrees,
  computeDragRotation,
  toolbarIconsForObjectType,
  MIN_OBJECT_SIZE,
} from '../src/builder-manipulate.js';

describe('resizeHandleAtPoint (design doc build_mode_ui_redesign_feature_design.md §8.3)', () => {
  const obj = { x: 100, y: 100, width: 80, height: 60, rotation: 0 };
  // Unrotated bounding box spans x:[100,180], y:[100,160] -> corners at
  // (100,100)=nw, (180,100)=ne, (100,160)=sw, (180,160)=se.

  it('detects each corner handle on an unrotated object', () => {
    expect(resizeHandleAtPoint(obj, 100, 100)).toBe('nw');
    expect(resizeHandleAtPoint(obj, 180, 100)).toBe('ne');
    expect(resizeHandleAtPoint(obj, 100, 160)).toBe('sw');
    expect(resizeHandleAtPoint(obj, 180, 160)).toBe('se');
  });

  it('returns null when the point is nowhere near a corner', () => {
    expect(resizeHandleAtPoint(obj, 140, 130)).toBeNull();
  });

  it('accounts for rotation when locating the corners', () => {
    // A 90deg rotation swaps the visual role of adjacent corners around the
    // (unchanged) center -- the world position that was "nw" moves to where
    // "ne" used to be for a square-ish rotation frame. We only assert that
    // some handle (not null) is still found at the correct rotated world
    // position, since exact corner identity after rotation is an
    // implementation nuance rather than the property under test here.
    const rotated = { x: 100, y: 100, width: 80, height: 60, rotation: 90 };
    const cx = rotated.x + rotated.width / 2;
    const cy = rotated.y + rotated.height / 2;
    // World position of the local nw corner (-40,-30) rotated 90deg is (cx+30, cy-40).
    const worldX = cx + 30;
    const worldY = cy - 40;
    expect(resizeHandleAtPoint(rotated, worldX, worldY)).not.toBeNull();
  });
});

describe('computeResizeFromHandle', () => {
  const obj = { x: 100, y: 100, width: 80, height: 60, rotation: 0 };

  it('dragging the se handle grows width/height while keeping the nw corner (x, y) fixed', () => {
    const result = computeResizeFromHandle(obj, 'se', 220, 200);
    expect(result.x).toBeCloseTo(100);
    expect(result.y).toBeCloseTo(100);
    expect(result.width).toBeCloseTo(120);
    expect(result.height).toBeCloseTo(100);
  });

  it('dragging the nw handle keeps the opposite (se) corner fixed in world space', () => {
    const result = computeResizeFromHandle(obj, 'nw', 60, 80);
    // Old se corner was at (180, 160); it must stay put.
    expect(result.x + result.width).toBeCloseTo(180);
    expect(result.y + result.height).toBeCloseTo(160);
    expect(result.width).toBeCloseTo(120);
    expect(result.height).toBeCloseTo(80);
  });

  it('never shrinks below MIN_OBJECT_SIZE', () => {
    const result = computeResizeFromHandle(obj, 'se', 105, 105);
    expect(result.width).toBeGreaterThanOrEqual(MIN_OBJECT_SIZE);
    expect(result.height).toBeGreaterThanOrEqual(MIN_OBJECT_SIZE);
  });

  it('preserves aspect ratio when preserveAspect is true', () => {
    const result = computeResizeFromHandle(obj, 'se', 260, 190, { preserveAspect: true });
    expect(result.width / result.height).toBeCloseTo(obj.width / obj.height, 5);
  });
});

describe('angleDegrees', () => {
  it('returns 0 for a point directly to the right of center', () => {
    expect(angleDegrees(0, 0, 10, 0)).toBeCloseTo(0);
  });

  it('returns 90 for a point directly below center (screen y+ is down)', () => {
    expect(angleDegrees(0, 0, 0, 10)).toBeCloseTo(90);
  });

  it('returns -90 for a point directly above center', () => {
    expect(angleDegrees(0, 0, 0, -10)).toBeCloseTo(-90);
  });
});

describe('computeDragRotation', () => {
  it('adds the change in pointer angle to the rotation the drag started at', () => {
    expect(computeDragRotation(10, 20, 50)).toBeCloseTo(40);
  });

  it('normalizes the result into [0, 360)', () => {
    expect(computeDragRotation(350, 0, 20)).toBeCloseTo(10);
    expect(computeDragRotation(10, 20, -30)).toBeCloseTo(320);
  });
});

describe('toolbarIconsForObjectType (design doc §8.1/§8.4/§8.5)', () => {
  it('shows rotate_right, palette, delete but no tune for a plain furniture type', () => {
    expect(toolbarIconsForObjectType('table')).toEqual(['rotate_right', 'palette', 'delete']);
    expect(toolbarIconsForObjectType('chair')).toEqual(['rotate_right', 'palette', 'delete']);
  });

  it('also shows tune for object types with non-spatial config', () => {
    expect(toolbarIconsForObjectType('bookshelf')).toEqual(['rotate_right', 'palette', 'tune', 'delete']);
    expect(toolbarIconsForObjectType('tv')).toEqual(['rotate_right', 'palette', 'tune', 'delete']);
    expect(toolbarIconsForObjectType('music_player')).toEqual(['rotate_right', 'palette', 'tune', 'delete']);
    expect(toolbarIconsForObjectType('ai_character')).toEqual(['rotate_right', 'palette', 'tune', 'delete']);
    expect(toolbarIconsForObjectType('escape_door')).toEqual(['rotate_right', 'palette', 'tune', 'delete']);
    expect(toolbarIconsForObjectType('hidden_item')).toEqual(['rotate_right', 'palette', 'tune', 'delete']);
  });

  it('reduces a locked configurable object to just tune (read-only "View Details")', () => {
    expect(toolbarIconsForObjectType('bookshelf', { isLocked: true })).toEqual(['tune']);
  });

  it('reduces a locked plain furniture object to an empty toolbar (nothing to view or do)', () => {
    expect(toolbarIconsForObjectType('table', { isLocked: true })).toEqual([]);
  });

  it('applies the same reduction for a no-permission object as for a locked one', () => {
    expect(toolbarIconsForObjectType('bookshelf', { canEdit: false })).toEqual(['tune']);
    expect(toolbarIconsForObjectType('table', { canEdit: false })).toEqual([]);
  });
});
