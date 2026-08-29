/**
 * Client-side copy — src/builder-catalog.js is the canonical source used by
 * tests. Furniture catalog metadata + filter-group derivation for the
 * Furniture tab's catalog grid (design doc
 * build_mode_ui_redesign_feature_design.md §7.1).
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

export function catalogFilterGroup(objectType) {
  if (ESCAPE_ROOM_TYPES.has(objectType)) return 'escape-room';
  const entry = CATALOG_ENTRIES.find((e) => e.objectType === objectType);
  return entry ? entry.category : 'furniture';
}

export function filterCatalogEntries(entries, { group = 'all', search = '' } = {}) {
  const query = (search || '').trim().toLowerCase();
  return (entries || []).filter((entry) => {
    const matchesGroup = group === 'all' || catalogFilterGroup(entry.objectType) === group;
    const matchesSearch = !query || entry.label.toLowerCase().includes(query);
    return matchesGroup && matchesSearch;
  });
}

export const CATALOG_FILTER_CHIPS = [
  { group: 'all', label: 'All' },
  { group: 'furniture', label: 'Furniture' },
  { group: 'interactive', label: 'Interactive' },
  { group: 'escape-room', label: 'Escape Room' },
];

const CATALOG_COLOR_DOT_PRESETS = ['natural-wood', 'dark-wood', 'white'];

const COLOR_DOT_HEX = {
  'natural-wood': '#c9975a',
  'dark-wood': '#5b3a29',
  white: '#f5f5f5',
};

export const CATALOG_COLOR_DOT_HEXES = CATALOG_COLOR_DOT_PRESETS.map((preset) => COLOR_DOT_HEX[preset]);
