/**
 * Phase K+: the 5 selectable "empty room" visual styles a user can choose
 * from when creating a custom room (Create Room panel). Unlike the fixed
 * Lobby (which keeps its own hardcoded look), a freshly created custom room
 * starts as a furniture-free shell — these presets control only the ambient
 * colors (backdrop, wall, floor) of that shell so it doesn't look like a
 * blank grey box while the room's owner builds it out via the room builder.
 */

export const ROOM_STYLES = [
  {
    id: 'modern-loft',
    label: 'Modern Loft',
    description: 'Cool industrial grays with a clean, open feel.',
    backdropTop: '#2b2f38',
    backdropBottom: '#1c1f26',
    wallTop: '#3d4350',
    wallBottom: '#5b6472',
    floorLight: '#8a8f98',
    floorDark: '#787d86',
  },
  {
    id: 'cozy-den',
    label: 'Cozy Den',
    description: 'Warm wood tones for a relaxed, homely lounge.',
    backdropTop: '#332417',
    backdropBottom: '#1f160d',
    wallTop: '#5c4128',
    wallBottom: '#7a5b3a',
    floorLight: '#a9784f',
    floorDark: '#96683f',
  },
  {
    id: 'sunlit-studio',
    label: 'Sunlit Studio',
    description: 'Bright creams and warm whites, airy and light.',
    backdropTop: '#f5ede1',
    backdropBottom: '#e8dcc8',
    wallTop: '#fdf6ec',
    wallBottom: '#eaddc6',
    floorLight: '#d8c9ab',
    floorDark: '#c9b795',
  },
  {
    id: 'midnight-lounge',
    label: 'Midnight Lounge',
    description: 'Deep purples and blues for a moody night-club vibe.',
    backdropTop: '#1a1530',
    backdropBottom: '#0e0b1c',
    wallTop: '#2b2150',
    wallBottom: '#463374',
    floorLight: '#463a6b',
    floorDark: '#3a2f59',
  },
  {
    id: 'minimalist-white',
    label: 'Minimalist White',
    description: 'Clean whites and light grays, ready for anything.',
    backdropTop: '#f4f4f4',
    backdropBottom: '#e0e0e0',
    wallTop: '#ffffff',
    wallBottom: '#eaeaea',
    floorLight: '#dcdcdc',
    floorDark: '#cfcfcf',
  },
];

export const DEFAULT_ROOM_STYLE = 'modern-loft';

/** Returns true if `styleId` matches one of the known ROOM_STYLES ids. */
export function isValidRoomStyle(styleId) {
  return ROOM_STYLES.some((style) => style.id === styleId);
}

/** Resolves a style id to its full preset object, falling back to the default style. */
export function resolveRoomStyle(styleId) {
  return ROOM_STYLES.find((style) => style.id === styleId) ?? resolveRoomStyle(DEFAULT_ROOM_STYLE);
}
