import { describe, it, expect } from 'vitest';
import { buildMiniMapCells, normalizeTileList, tileKey } from '../src/world-map.js';

describe('world-map helpers', () => {
  it('normalizes tiles and removes invalid items', () => {
    const tiles = normalizeTileList([{ x: 0, y: 0 }, { x: 1, y: -1 }, { bad: true }]);
    expect(tiles).toEqual([{ x: 0, y: 0 }, { x: 1, y: -1 }]);
  });

  it('builds a 5x5 minimap projection with active and current flags', () => {
    const cells = buildMiniMapCells([{ x: 0, y: 0 }, { x: 1, y: 0 }], { x: 1, y: 0 });
    expect(cells.length).toBe(25);
    const active = cells.filter((c) => c.active);
    expect(active).toHaveLength(2);
    const current = cells.find((c) => c.current);
    expect(current).toMatchObject({ x: 1, y: 0, active: true, current: true });
  });

  it('creates stable tile keys', () => {
    expect(tileKey({ x: -2, y: 2 })).toBe('-2:2');
  });
});
