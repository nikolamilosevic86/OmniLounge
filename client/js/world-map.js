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
