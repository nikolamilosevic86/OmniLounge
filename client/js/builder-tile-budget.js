/**
 * Client-side copy — src/builder-tile-budget.js is the canonical source used
 * by tests. Tile-object-budget helpers for the drag-to-place preview tint
 * (design doc build_mode_ui_redesign_feature_design.md §7.2).
 */

export const MAX_OBJECTS_PER_TILE = 40;

export const BUDGET_WARNING_THRESHOLD = 5;

function tileKeyFor(tile) {
  if (Array.isArray(tile)) return `${tile[0]},${tile[1]}`;
  return `${tile?.x ?? 0},${tile?.y ?? 0}`;
}

export function countObjectsOnTile(objects, tile) {
  const key = tileKeyFor(tile);
  return (objects || []).filter((obj) => tileKeyFor(obj.tile) === key).length;
}

export function isTileNearObjectBudget(objects, tile, threshold = BUDGET_WARNING_THRESHOLD) {
  return countObjectsOnTile(objects, tile) >= MAX_OBJECTS_PER_TILE - threshold;
}
