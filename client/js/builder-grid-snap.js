/**
 * Grid snapping (design doc feature_designs/build_mode_ui_redesign_feature_design.md
 * section 12). Purely a client-side rounding step applied to coordinates
 * before they're sent in the existing `room:object:create`/`room:object:move`
 * payloads -- no server change is needed, since the server already accepts
 * arbitrary float x/y.
 */

export const DEFAULT_GRID_SIZE = 20;

/** Rounds a single coordinate to the nearest grid line. */
export function snapToGrid(value, gridSize = DEFAULT_GRID_SIZE) {
  // `|| 0` normalizes the -0 that Math.round can produce for small negative
  // inputs (e.g. -9) into a plain 0, which is what callers/tests expect.
  return (Math.round(value / gridSize) * gridSize) || 0;
}

/** Snaps both axes of a point to the grid, or returns it unchanged when snapping is disabled. */
export function snapPoint(point, enabled, gridSize = DEFAULT_GRID_SIZE) {
  if (!enabled) return point;
  return { x: snapToGrid(point.x, gridSize), y: snapToGrid(point.y, gridSize) };
}
