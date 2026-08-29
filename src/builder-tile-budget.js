/**
 * Client-side tile-object-budget helpers for the drag-to-place preview tint
 * (design doc build_mode_ui_redesign_feature_design.md §7.2). There is NO
 * server-side overlap-blocking rule (confirmed against
 * server/game/room_builder.py) -- only a per-tile object-count cap,
 * `MAX_OBJECTS_PER_TILE = 40`. This module mirrors that cap client-side so
 * the drag ghost can show an amber "you're near the limit" tint, never a
 * red/green "can/can't place here" tint (no such rule exists to advertise).
 */

// Mirror of server/game/room_builder.py's MAX_OBJECTS_PER_TILE.
export const MAX_OBJECTS_PER_TILE = 40;

// "at or within a few objects of its budget" (§7.2).
export const BUDGET_WARNING_THRESHOLD = 5;

function tileKeyFor(tile) {
  if (Array.isArray(tile)) return `${tile[0]},${tile[1]}`;
  return `${tile?.x ?? 0},${tile?.y ?? 0}`;
}

/** Counts builder objects sitting on the given tile (array `[x, y]` or `{x, y}`, either shape). */
export function countObjectsOnTile(objects, tile) {
  const key = tileKeyFor(tile);
  return (objects || []).filter((obj) => tileKeyFor(obj.tile) === key).length;
}

/** True once a tile is at or within `threshold` objects of MAX_OBJECTS_PER_TILE. */
export function isTileNearObjectBudget(objects, tile, threshold = BUDGET_WARNING_THRESHOLD) {
  return countObjectsOnTile(objects, tile) >= MAX_OBJECTS_PER_TILE - threshold;
}
