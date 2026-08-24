/**
 * Animation helpers for avatar walk cycle.
 * (Client-side copy — src/animation.js is the canonical source used by tests.)
 */

export const WALK_PHASE_INCREMENT = 0.06;

export function advanceWalkPhase(phase, moved, increment = WALK_PHASE_INCREMENT) {
  if (!moved) return phase;
  return (phase + increment) % 1;
}
