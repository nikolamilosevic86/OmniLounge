import { describe, it, expect } from 'vitest';
import {
  CATALOG_ENTRIES,
  CATALOG_FILTER_CHIPS,
  catalogFilterGroup,
  filterCatalogEntries,
  CATALOG_COLOR_DOT_HEXES,
} from '../src/builder-catalog.js';

describe('CATALOG_ENTRIES (design doc build_mode_ui_redesign_feature_design.md section 7.1)', () => {
  it('has exactly one entry per OBJECT_TYPE_CATALOG type', () => {
    const types = CATALOG_ENTRIES.map((e) => e.objectType);
    expect(types).toEqual([
      'table', 'chair', 'bar', 'sofa', 'bookshelf', 'tv', 'music_player', 'ai_character', 'escape_door', 'hidden_item',
    ]);
  });

  it('gives every entry a non-empty label', () => {
    CATALOG_ENTRIES.forEach((e) => expect(typeof e.label).toBe('string'));
    expect(CATALOG_ENTRIES.every((e) => e.label.length > 0)).toBe(true);
  });
});

describe('catalogFilterGroup', () => {
  it('groups the 4 static furniture types as "furniture"', () => {
    expect(catalogFilterGroup('table')).toBe('furniture');
    expect(catalogFilterGroup('chair')).toBe('furniture');
    expect(catalogFilterGroup('bar')).toBe('furniture');
    expect(catalogFilterGroup('sofa')).toBe('furniture');
  });

  it('groups bookshelf/tv/music_player/ai_character as "interactive"', () => {
    expect(catalogFilterGroup('bookshelf')).toBe('interactive');
    expect(catalogFilterGroup('tv')).toBe('interactive');
    expect(catalogFilterGroup('music_player')).toBe('interactive');
    expect(catalogFilterGroup('ai_character')).toBe('interactive');
  });

  it('carves escape_door/hidden_item out of "interactive" into their own "escape-room" group', () => {
    expect(catalogFilterGroup('escape_door')).toBe('escape-room');
    expect(catalogFilterGroup('hidden_item')).toBe('escape-room');
  });
});

describe('filterCatalogEntries', () => {
  it('returns every entry for the "all" group with no search', () => {
    expect(filterCatalogEntries(CATALOG_ENTRIES, { group: 'all', search: '' })).toHaveLength(10);
  });

  it('narrows to exactly the 4 furniture-group entries', () => {
    const result = filterCatalogEntries(CATALOG_ENTRIES, { group: 'furniture' });
    expect(result.map((e) => e.objectType)).toEqual(['table', 'chair', 'bar', 'sofa']);
  });

  it('narrows to exactly the 2 escape-room-group entries', () => {
    const result = filterCatalogEntries(CATALOG_ENTRIES, { group: 'escape-room' });
    expect(result.map((e) => e.objectType)).toEqual(['escape_door', 'hidden_item']);
  });

  it('narrows by a case-insensitive label search regardless of active group', () => {
    const result = filterCatalogEntries(CATALOG_ENTRIES, { group: 'all', search: 'sh' });
    expect(result.map((e) => e.objectType)).toEqual(['bookshelf']);
  });

  it('combines group and search filters', () => {
    const result = filterCatalogEntries(CATALOG_ENTRIES, { group: 'furniture', search: 'bar' });
    expect(result.map((e) => e.objectType)).toEqual(['bar']);
  });

  it('defaults to the "all" group and empty search when omitted', () => {
    expect(filterCatalogEntries(CATALOG_ENTRIES)).toHaveLength(10);
  });

  it('tolerates a missing/undefined entries list', () => {
    expect(filterCatalogEntries(undefined, { group: 'all' })).toEqual([]);
  });
});

describe('CATALOG_FILTER_CHIPS', () => {
  it('lists All first, followed by Furniture, Interactive, Escape Room', () => {
    expect(CATALOG_FILTER_CHIPS.map((c) => c.group)).toEqual(['all', 'furniture', 'interactive', 'escape-room']);
  });
});

describe('CATALOG_COLOR_DOT_HEXES', () => {
  it('has exactly 3 hex colors for the quiet "more colors exist" hint', () => {
    expect(CATALOG_COLOR_DOT_HEXES).toHaveLength(3);
    CATALOG_COLOR_DOT_HEXES.forEach((hex) => expect(hex).toMatch(/^#[0-9a-f]{6}$/i));
  });
});
