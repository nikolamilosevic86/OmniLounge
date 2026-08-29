export function tileKey(tile) {
  return `${tile.x}:${tile.y}`;
}

export function normalizeTileList(rawTiles = []) {
  return rawTiles
    .filter((tile) => Number.isInteger(tile?.x) && Number.isInteger(tile?.y))
    .map((tile) => ({ x: tile.x, y: tile.y }));
}

export function buildMiniMapCells(tiles = [], currentTile = { x: 0, y: 0 }) {
  const normalized = normalizeTileList(tiles);
  const active = new Set(normalized.map(tileKey));
  const cells = [];

  for (let y = -2; y <= 2; y += 1) {
    for (let x = -2; x <= 2; x += 1) {
      const key = tileKey({ x, y });
      cells.push({
        x,
        y,
        key,
        active: active.has(key),
        current: currentTile?.x === x && currentTile?.y === y,
      });
    }
  }

  return cells;
}

/**
 * Per-edge neighbor-tile presence for `currentTile` (design doc
 * feature_designs/build_mode_ui_redesign_feature_design.md §10.2). Drives
 * whether room-renderer.js draws a walkable doorway (neighbor exists) or a
 * capped wall/rail (no neighbor) on each of the four tile edges. Reuses the
 * exact same `tiles`/`currentTile` pairing buildMiniMapCells already consumes
 * -- no new event or payload is needed.
 */
export function neighborTileFlags(tiles = [], currentTile = { x: 0, y: 0 }) {
  const active = new Set(normalizeTileList(tiles).map(tileKey));
  const { x, y } = currentTile;
  return {
    top: active.has(tileKey({ x, y: y - 1 })),
    bottom: active.has(tileKey({ x, y: y + 1 })),
    left: active.has(tileKey({ x: x - 1, y })),
    right: active.has(tileKey({ x: x + 1, y })),
  };
}
