/**
 * Client-side rules for AI-character guided tours ("follow me").
 *
 * Kept free of DOM and socket access so the decisions that drive the tour
 * UI -- who may be offered a tour, whether the local player is currently
 * following one, and how a `room:npc:moved` broadcast is folded into the
 * cached builder objects -- can be unit tested. `client/js/main.js` itself
 * is not importable by the test suite (it touches `document` at module
 * load), so any logic worth asserting on lives here.
 */

/** Longest a waypoint note may be; mirrors MAX_WAYPOINT_LABEL_LENGTH server-side. */
export const MAX_WAYPOINT_LABEL_LENGTH = 120;

/** How long an NPC speech bubble stays on screen, in ms. */
export const NPC_BUBBLE_DURATION_MS = 4000;

/**
 * True when this object is an AI character with at least one tour stop, and
 * so can meaningfully offer to guide a visitor.
 */
export function characterOffersTour(object) {
  if (!object || object.objectType !== 'ai_character') return false;
  return Array.isArray(object.waypoints) && object.waypoints.length > 0;
}

/** True when `playerId` is currently following this character's tour. */
export function isFollowingTour(object, playerId) {
  const followers = object?.tour?.followers;
  if (!Array.isArray(followers) || !playerId) return false;
  return followers.includes(playerId);
}

/**
 * Decide which of the dialogue modal's tour buttons should be visible.
 * Exactly one (or neither) is shown, never both: offering to follow a guide
 * you are already following is meaningless, and so is offering to stop a
 * tour you never joined.
 */
export function tourButtonState(object, playerId) {
  if (!characterOffersTour(object)) return { follow: false, stop: false };
  return isFollowingTour(object, playerId)
    ? { follow: false, stop: true }
    : { follow: true, stop: false };
}

/** Human-readable progress line for a tour, or '' when no tour is running. */
export function formatTourStatus(tour) {
  if (!tour || !tour.status) return '';
  if (tour.status === 'returning') return 'Heading back...';
  if (tour.status === 'finished') return 'Tour complete';
  const total = tour.waypointCount || 0;
  const current = Math.min((tour.waypointIndex || 0) + 1, total);
  const suffix = total ? ` (stop ${current} of ${total})` : '';
  return (tour.status === 'paused' ? 'Explaining' : 'Walking') + suffix;
}

/**
 * Apply a `room:npc:moved` broadcast to the cached builder objects.
 *
 * Returns a new array (never mutates the input) so callers can compare
 * references to decide whether to re-render. Unknown object ids are ignored
 * rather than throwing: a move can arrive for a character on a tile whose
 * objects this client has not loaded, or in the gap after a delete.
 */
export function applyNpcMove(objects, payload) {
  if (!Array.isArray(objects) || !payload?.objectId || !payload.position) return objects;
  let changed = false;
  const next = objects.map((obj) => {
    if (obj.objectId !== payload.objectId) return obj;
    changed = true;
    return {
      ...obj,
      x: payload.position.x,
      y: payload.position.y,
      tour: payload.finished ? null : { ...(obj.tour || {}), status: payload.status, waypointIndex: payload.waypointIndex },
    };
  });
  return changed ? next : objects;
}

/**
 * Validate a tour stop note before sending it. Returns the trimmed label, or
 * null for an empty one (a stop with no note is legal -- the character just
 * walks there silently).
 */
export function normalizeWaypointLabel(raw) {
  const trimmed = (raw ?? '').trim();
  if (!trimmed) return null;
  if (trimmed.length > MAX_WAYPOINT_LABEL_LENGTH) {
    throw new Error(`Stop note must be ${MAX_WAYPOINT_LABEL_LENGTH} characters or fewer.`);
  }
  return trimmed;
}
