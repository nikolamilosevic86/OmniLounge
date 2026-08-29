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
  // Puzzle props (escape_room_feature_design.md §5.4) -- the physical
  // shapes a puzzle can wear in the room.
  { objectType: 'cipher_box', label: 'Cipher Box', category: 'interactive' },
  { objectType: 'digital_lock', label: 'Digital Lock', category: 'interactive' },
  { objectType: 'combination_dial', label: 'Combination Dial', category: 'interactive' },
  { objectType: 'riddle_tablet', label: 'Riddle Tablet', category: 'interactive' },
  { objectType: 'clue_board', label: 'Clue Board', category: 'interactive' },
];

/** The five puzzle-prop shapes, mirroring server/game/room_object_catalog.py's
 * `PUZZLE_PROP_TYPES` (same order, so the catalog grid and the puzzle-shape
 * picker present them identically). */
export const PUZZLE_PROP_TYPES = [
  'cipher_box',
  'digital_lock',
  'combination_dial',
  'riddle_tablet',
  'clue_board',
];

const ESCAPE_ROOM_TYPES = new Set(['escape_door', 'hidden_item', ...PUZZLE_PROP_TYPES]);

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
