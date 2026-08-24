/**
 * Animation helpers for avatar walk cycle.
 *
 * The walk phase is a value in [0, 1) representing one full stride cycle.
 * It advances each frame while the player is moving and freezes when stopped.
 */

/** How much the walk phase advances per render frame (~30 fps → ~1.8 strides/sec). */
export const WALK_PHASE_INCREMENT = 0.06;

/**
 * Advance the walk phase by one render frame.
 *
 * @param {number} phase    Current phase in [0, 1).
 * @param {boolean} moved   Whether the player moved since the last frame.
 * @param {number} increment Amount to advance per frame (default WALK_PHASE_INCREMENT).
 * @returns {number} New phase in [0, 1).
 */
export function advanceWalkPhase(phase, moved, increment = WALK_PHASE_INCREMENT) {
  if (!moved) return phase;
  return (phase + increment) % 1;
}
