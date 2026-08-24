/**
 * Defines every interactive room object, its click zone, and available actions.
 *
 * Collision zones (from movement.js) use an 8-pixel margin, so obstacle blocked
 * ranges are:
 *   sofa-left  : x ∈ [40,222]  y ∈ [322,418]
 *   sofa-right : x ∈ [570,752] y ∈ [322,418]
 *   table      : x ∈ [340,460] y ∈ [362,420]
 *   dj-deck    : x ∈ [110,190] y ∈ [422,484]
 *
 * Action targets are placed just outside those blocked ranges so the pathfinding
 * can actually reach them.  "on-table" is a special teleport (server bypasses
 * collision for it).
 */

export const ROOM_OBJECTS = [
  {
    id: 'sofa-left',
    label: 'Sofa',
    icon: '🛋️',
    zone: { x: 48, y: 316, w: 168, h: 110 },
    actions: [
      { id: 'sit',    icon: '🪑', label: 'Sit down',  actionState: 'sitting',  target: { x: 125, y: 422 } },
      { id: 'lounge', icon: '😴', label: 'Lounge',    actionState: 'lounging', target: { x:  95, y: 422 } },
      { id: 'stand',  icon: '🚶', label: 'Get up',    actionState: null,       target: { x: 125, y: 432 } },
    ],
  },
  {
    id: 'sofa-right',
    label: 'Sofa',
    icon: '🛋️',
    zone: { x: 578, y: 316, w: 168, h: 110 },
    actions: [
      { id: 'sit',    icon: '🪑', label: 'Sit down',  actionState: 'sitting',  target: { x: 655, y: 422 } },
      { id: 'lounge', icon: '😴', label: 'Lounge',    actionState: 'lounging', target: { x: 685, y: 422 } },
      { id: 'stand',  icon: '🚶', label: 'Get up',    actionState: null,       target: { x: 655, y: 432 } },
    ],
  },
  {
    id: 'coffee-table',
    label: 'Coffee Table',
    icon: '☕',
    zone: { x: 335, y: 355, w: 130, h: 75 },
    actions: [
      { id: 'drink',    icon: '☕', label: 'Grab coffee',  actionState: 'drinking', target: { x: 335, y: 424 } },
      { id: 'sit-edge', icon: '🪑', label: 'Sit on edge',  actionState: 'sitting',  target: { x: 462, y: 424 } },
      { id: 'climb',    icon: '⬆️', label: 'Climb on',     actionState: 'on-table', target: { x: 400, y: 354 } },
      { id: 'stand',    icon: '🚶', label: 'Get up',       actionState: null,       target: { x: 400, y: 432 } },
    ],
  },
  {
    id: 'dj-deck',
    label: 'DJ Deck',
    icon: '🎧',
    zone: { x: 112, y: 418, w: 76, h: 70 },
    actions: [
      { id: 'dj',    icon: '🎵', label: 'DJ here',    actionState: 'djing',   target: { x: 148, y: 488 } },
      { id: 'dance', icon: '💃', label: 'Dance here',  actionState: 'dancing', target: { x: 192, y: 488 } },
      { id: 'stand', icon: '🚶', label: 'Walk away',   actionState: null,      target: { x: 148, y: 498 } },
    ],
  },
];

/** Returns the first ROOM_OBJECT whose zone contains (x, y), or null. */
export function getObjectAtPoint(x, y) {
  return ROOM_OBJECTS.find(o =>
    x >= o.zone.x && x <= o.zone.x + o.zone.w &&
    y >= o.zone.y && y <= o.zone.y + o.zone.h
  ) ?? null;
}
