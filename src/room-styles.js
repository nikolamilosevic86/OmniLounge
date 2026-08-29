/**
 * Phase K+: the 8 selectable "empty room" visual styles a user can choose
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
    lightColor: '190, 210, 235',
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
    lightColor: '255, 190, 120',
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
    lightColor: '255, 250, 230',
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
    lightColor: '180, 140, 255',
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
    lightColor: '245, 245, 250',
  },
  {
    id: 'beach-cabana',
    label: 'Beach Cabana',
    description: 'Sunny turquoise sky and warm sand, a breezy tropical escape.',
    backdropTop: '#8fd9e8',
    backdropBottom: '#5bb8d4',
    wallTop: '#eaf6f2',
    wallBottom: '#bfe8dd',
    floorLight: '#e8d5a8',
    floorDark: '#d9c08a',
    lightColor: '255, 235, 180',
  },
  {
    id: 'retro-arcade',
    label: 'Retro Arcade',
    description: 'Neon magenta and cyan glowing against a moody 80s dark room.',
    backdropTop: '#170a29',
    backdropBottom: '#0a0414',
    wallTop: '#2a1045',
    wallBottom: '#4a1868',
    floorLight: '#241238',
    floorDark: '#180b26',
    lightColor: '255, 60, 220',
  },
  {
    id: 'enchanted-garden',
    label: 'Enchanted Garden',
    description: 'Soft pastel greens and dappled daylight, like a hidden grove.',
    backdropTop: '#c9ead0',
    backdropBottom: '#a3d9ae',
    wallTop: '#e8f5e0',
    wallBottom: '#c3e6c0',
    floorLight: '#9fcf9a',
    floorDark: '#88bf82',
    lightColor: '210, 255, 200',
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
