import { describe, it, expect } from 'vitest';
import { buildMiniMapCells, normalizeTileList, tileKey, neighborTileFlags } from '../src/world-map.js';

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

describe('neighborTileFlags (design doc build_mode_ui_redesign_feature_design.md §10.2)', () => {
  it('reports all four edges closed when no neighbor tiles exist', () => {
    const flags = neighborTileFlags([{ x: 0, y: 0 }], { x: 0, y: 0 });
    expect(flags).toEqual({ top: false, bottom: false, left: false, right: false });
  });

  it('reports an edge open only where a neighbor tile actually exists', () => {
    const tiles = [{ x: 0, y: 0 }, { x: 0, y: -1 }, { x: 1, y: 0 }];
    const flags = neighborTileFlags(tiles, { x: 0, y: 0 });
    expect(flags).toEqual({ top: true, bottom: false, left: false, right: true });
  });

  it('reports all four edges open when surrounded on every side', () => {
    const tiles = [
      { x: 0, y: 0 },
      { x: 0, y: -1 },
      { x: 0, y: 1 },
      { x: -1, y: 0 },
      { x: 1, y: 0 },
    ];
    const flags = neighborTileFlags(tiles, { x: 0, y: 0 });
    expect(flags).toEqual({ top: true, bottom: true, left: true, right: true });
  });

  it('ignores invalid tile entries the same way normalizeTileList does', () => {
    const flags = neighborTileFlags([{ x: 0, y: 0 }, { bad: true }, { x: 0, y: -1 }], { x: 0, y: 0 });
    expect(flags.top).toBe(true);
  });

  it('works for a currentTile away from the origin', () => {
    const tiles = [{ x: 3, y: 3 }, { x: 4, y: 3 }];
    const flags = neighborTileFlags(tiles, { x: 3, y: 3 });
    expect(flags).toEqual({ top: false, bottom: false, left: false, right: true });
  });
});
