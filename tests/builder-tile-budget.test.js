import { describe, it, expect } from 'vitest';
import {
  MAX_OBJECTS_PER_TILE,
  BUDGET_WARNING_THRESHOLD,
  countObjectsOnTile,
  isTileNearObjectBudget,
} from '../src/builder-tile-budget.js';

function objectsOnTile(tile, count) {
  return Array.from({ length: count }, (_, i) => ({ objectId: `o${i}`, tile }));
}

describe('MAX_OBJECTS_PER_TILE mirror (server/game/room_builder.py)', () => {
  it('matches the server-side budget of 40', () => {
    expect(MAX_OBJECTS_PER_TILE).toBe(40);
  });
});

describe('countObjectsOnTile', () => {
  it('counts only objects on the given [x, y]-array-tile', () => {
    const objects = [
      ...objectsOnTile([0, 0], 3),
      ...objectsOnTile([1, 0], 2),
    ];
    expect(countObjectsOnTile(objects, [0, 0])).toBe(3);
    expect(countObjectsOnTile(objects, [1, 0])).toBe(2);
    expect(countObjectsOnTile(objects, [5, 5])).toBe(0);
  });

  it('matches a {x, y}-object-tile against an [x, y]-array-tile', () => {
    const objects = objectsOnTile([2, 3], 4);
    expect(countObjectsOnTile(objects, { x: 2, y: 3 })).toBe(4);
  });

  it('tolerates a missing/undefined objects list', () => {
    expect(countObjectsOnTile(undefined, [0, 0])).toBe(0);
  });
});

describe('isTileNearObjectBudget (design doc build_mode_ui_redesign_feature_design.md §7.2)', () => {
  it('is false when nowhere near the budget', () => {
    const objects = objectsOnTile([0, 0], 3);
    expect(isTileNearObjectBudget(objects, [0, 0])).toBe(false);
  });

  it('is true once within BUDGET_WARNING_THRESHOLD objects of the cap', () => {
    const objects = objectsOnTile([0, 0], MAX_OBJECTS_PER_TILE - BUDGET_WARNING_THRESHOLD);
    expect(isTileNearObjectBudget(objects, [0, 0])).toBe(true);
  });

  it('is true at and beyond the cap itself', () => {
    const objects = objectsOnTile([0, 0], MAX_OBJECTS_PER_TILE);
    expect(isTileNearObjectBudget(objects, [0, 0])).toBe(true);
  });

  it('never treats a different tile as near budget', () => {
    const objects = objectsOnTile([0, 0], MAX_OBJECTS_PER_TILE);
    expect(isTileNearObjectBudget(objects, [9, 9])).toBe(false);
  });

  it('accepts a custom threshold override', () => {
    const objects = objectsOnTile([0, 0], MAX_OBJECTS_PER_TILE - 10);
    expect(isTileNearObjectBudget(objects, [0, 0], 5)).toBe(false);
    expect(isTileNearObjectBudget(objects, [0, 0], 10)).toBe(true);
  });
});
