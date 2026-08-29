/**
 * Pure client-side helpers for rendering and interacting with builder-placed
 * room objects (Phase E). Object `x`/`y` are treated as the top-left corner
 * of the object's bounding box, matching the server's `RoomBuilderState`
 * geometry and the existing `room-objects.js` zone convention.
 */

const COLOR_HEX = {
  'natural-wood': '#c9975a',
  'dark-wood': '#5b3a29',
  white: '#f5f5f5',
  black: '#222222',
  navy: '#1f3a5f',
  'forest-green': '#2f5233',
  burgundy: '#5c1a2b',
  'gold-accent': '#d4af37',
};

const DEFAULT_COLOR = '#7a6f93';

const TYPE_ICONS = {
  table: '🍽️',
  chair: '🪑',
  bar: '🍸',
  sofa: '🛋️',
  bookshelf: '📚',
  tv: '📺',
  music_player: '🎵',
  ai_character: '🧑‍🏫',
  escape_door: '🚪',
  hidden_item: '🗝️',
};

const DEFAULT_TYPE_ICON = '🧩';

const INTERACTION_ICONS = {
  sit: '🪑',
  lounge: '😴',
  gather: '🙌',
  browse_books: '📖',
  resume_reading: '🔖',
  watch_video: '🎬',
  open_playlist: '📃',
  play_track: '▶️',
  view_playlist: '🎼',
  talk: '💬',
  ask_hint: '❓',
  start_mission: '🚀',
  attempt_open: '🚪',
  pick_up: '🖐️',
  solve_puzzle: '🧩',
};

const DEFAULT_INTERACTION_ICON = '✨';

/** Returns the topmost builder object (highest zIndex) whose bounds contain (x, y), or null. */
export function getBuilderObjectAtPoint(objects, x, y) {
  for (let i = objects.length - 1; i >= 0; i--) {
    const obj = objects[i];
    if (x >= obj.x && x <= obj.x + obj.width && y >= obj.y && y <= obj.y + obj.height) {
      return obj;
    }
  }
  return null;
}

/** Resolves a Phase E color preset to a hex color, falling back to a neutral default. */
export function resolveObjectColor(colorPreset) {
  return COLOR_HEX[colorPreset] ?? DEFAULT_COLOR;
}

/** Returns a display icon for a builder object type, falling back to a generic icon. */
export function objectTypeIcon(objectType) {
  return TYPE_ICONS[objectType] ?? DEFAULT_TYPE_ICON;
}

/** Maps a server-provided interaction menu into radial-menu-compatible action items. */
export function buildInteractionActions(interactions) {
  return interactions.map((interaction) => ({
    icon: INTERACTION_ICONS[interaction.interactionType] ?? DEFAULT_INTERACTION_ICON,
    label: interaction.label,
    interactionType: interaction.interactionType,
    actionState: interaction.actionState ?? null,
  }));
}

/**
 * Keyboard Tab-cycle selection (design doc
 * feature_designs/build_mode_ui_redesign_feature_design.md §13). Advances
 * (direction=1) or retreats (direction=-1) through `objects` in the stable
 * order they're already given -- the same order the server returns them in --
 * wrapping around at either end. Falls back to selecting the first (or last,
 * when cycling backward) object when nothing is currently selected, or when
 * the previously-selected id no longer exists in the list (e.g. it was just
 * deleted).
 */
export function cycleSelectedObjectId(objects, currentSelectedId, direction = 1) {
  if (!Array.isArray(objects) || objects.length === 0) return null;
  const ids = objects.map((obj) => obj.objectId);
  const currentIndex = ids.indexOf(currentSelectedId);
  if (currentIndex === -1) {
    return direction < 0 ? ids[ids.length - 1] : ids[0];
  }
  const nextIndex = (currentIndex + direction + ids.length) % ids.length;
  return ids[nextIndex];
}
