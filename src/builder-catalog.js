/**
 * Client-side furniture catalog metadata + filter-group derivation for the
 * Furniture tab's catalog grid (design doc
 * build_mode_ui_redesign_feature_design.md §7.1), replacing the
 * type/size/color/material dropdown stack. Mirrors
 * server/game/room_object_catalog.py's `OBJECT_TYPE_CATALOG` (labels +
 * category only -- size/interaction data isn't needed for the grid itself).
 *
 * §7.1 explicitly calls out that `OBJECT_TYPE_CATALOG` only has 2 real
 * `category` values ("furniture"/"interactive"), which would bury the
 * escape-room-specific types inside a 6-item "Interactive" bucket -- so the
 * filter groups below are a client-side derived lookup, NOT a raw
 * pass-through of the server's `category` field: escape_door/hidden_item are
 * carved out of "interactive" into their own "escape-room" group.
 */

export const CATALOG_ENTRIES = [
  { objectType: 'table', label: 'Table', category: 'furniture' },
  { objectType: 'chair', label: 'Chair', category: 'furniture' },
  { objectType: 'bar', label: 'Bar', category: 'furniture' },
  { objectType: 'sofa', label: 'Sofa', category: 'furniture' },
  { objectType: 'bookshelf', label: 'Bookshelf', category: 'interactive' },
  { objectType: 'tv', label: 'TV', category: 'interactive' },
  { objectType: 'music_player', label: 'Music Player', category: 'interactive' },
  { objectType: 'ai_character', label: 'AI Character', category: 'interactive' },
  { objectType: 'escape_door', label: 'Escape Door', category: 'interactive' },
  { objectType: 'hidden_item', label: 'Hidden Item', category: 'interactive' },
];

const ESCAPE_ROOM_TYPES = new Set(['escape_door', 'hidden_item']);

/** Client-only filter group for a catalog entry: "furniture" | "interactive" | "escape-room". */
export function catalogFilterGroup(objectType) {
  if (ESCAPE_ROOM_TYPES.has(objectType)) return 'escape-room';
  const entry = CATALOG_ENTRIES.find((e) => e.objectType === objectType);
  return entry ? entry.category : 'furniture';
}

/**
 * Filters the catalog grid by chip group and/or label search (§7.1). Both
 * filters operate over the same in-memory list regardless of which chip is
 * active -- there is only one catalog grid, never a duplicated one per chip.
 */
export function filterCatalogEntries(entries, { group = 'all', search = '' } = {}) {
  const query = (search || '').trim().toLowerCase();
  return (entries || []).filter((entry) => {
    const matchesGroup = group === 'all' || catalogFilterGroup(entry.objectType) === group;
    const matchesSearch = !query || entry.label.toLowerCase().includes(query);
    return matchesGroup && matchesSearch;
  });
}

/** Filter chip row (§7.1): "All" first, the least-surprising default. */
export const CATALOG_FILTER_CHIPS = [
  { group: 'all', label: 'All' },
  { group: 'furniture', label: 'Furniture' },
  { group: 'interactive', label: 'Interactive' },
  { group: 'escape-room', label: 'Escape Room' },
];

// Same order as server/game/room_object_catalog.py's COLOR_PRESETS -- only
// the first 3 are used for the catalog card's quiet "more colors exist" dot
// hint (§7.1's "Resolved" note / §17 Decision D3), not the full 8-color set.
const CATALOG_COLOR_DOT_PRESETS = ['natural-wood', 'dark-wood', 'white'];

const COLOR_DOT_HEX = {
  'natural-wood': '#c9975a',
  'dark-wood': '#5b3a29',
  white: '#f5f5f5',
};

/** The 3 static dot colors every catalog card shows as a "more colors exist" hint. */
export const CATALOG_COLOR_DOT_HEXES = CATALOG_COLOR_DOT_PRESETS.map((preset) => COLOR_DOT_HEX[preset]);
