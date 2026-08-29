/**
 * Pure geometry + decision logic for on-canvas direct manipulation of
 * builder objects (design doc build_mode_ui_redesign_feature_design.md
 * §8.2/§8.3/§8.4/§8.5). Kept dependency-free from the canvas/DOM so the
 * math is unit-testable; client/js/main.js wires the actual pointer events.
 *
 * Coordinate convention matches client/js/room-renderer.js's
 * drawBuilderObjects: `obj.x`/`obj.y` is the top-left of the UNROTATED
 * bounding box; rendering translates to the center then rotates by
 * `obj.rotation` degrees (clockwise, since screen y+ points down) before
 * drawing the sprite at local (0,0). A "local" point below means relative
 * to the object's center, in that same unrotated frame.
 */

// A UX floor, not a server rule (the server only requires width/height > 0,
// server/game/room_builder_models.py's validate_positive_geometry) -- this
// just stops a corner-drag from collapsing an object into an invisible
// sliver or crossing zero (which would flip the object inside-out).
export const MIN_OBJECT_SIZE = 16;

const HANDLE_SIGN = {
  nw: { sx: -1, sy: -1 },
  ne: { sx: 1, sy: -1 },
  sw: { sx: -1, sy: 1 },
  se: { sx: 1, sy: 1 },
};

function toRad(deg) {
  return (deg * Math.PI) / 180;
}

function objectCenter(obj) {
  return { cx: obj.x + obj.width / 2, cy: obj.y + obj.height / 2 };
}

/** World (room) point -> the object's local, unrotated frame relative to its own center. */
function worldToLocal(obj, worldX, worldY) {
  const { cx, cy } = objectCenter(obj);
  const dx = worldX - cx;
  const dy = worldY - cy;
  const theta = toRad(obj.rotation || 0);
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  // Inverse of the rotation applied when rendering (R(-theta)).
  return { lx: dx * cos + dy * sin, ly: -dx * sin + dy * cos };
}

/** The object's local (unrotated, center-relative) frame -> a world (room) point. */
function localToWorld(obj, lx, ly) {
  const { cx, cy } = objectCenter(obj);
  const theta = toRad(obj.rotation || 0);
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  return { x: cx + lx * cos - ly * sin, y: cy + lx * sin + ly * cos };
}

/**
 * Which corner resize handle (if any) sits under a room-space point, given
 * the object's current geometry. `handleRadius` is the hit-test tolerance
 * around each corner, in room-space pixels.
 */
export function resizeHandleAtPoint(obj, pointerX, pointerY, handleRadius = 10) {
  const { lx, ly } = worldToLocal(obj, pointerX, pointerY);
  const hw = obj.width / 2;
  const hh = obj.height / 2;
  let closest = null;
  let closestDist = handleRadius;
  for (const [name, { sx, sy }] of Object.entries(HANDLE_SIGN)) {
    const dist = Math.hypot(lx - sx * hw, ly - sy * hh);
    if (dist <= closestDist) {
      closest = name;
      closestDist = dist;
    }
  }
  return closest;
}

/**
 * Computes the new `{x, y, width, height}` for dragging `handle` to the
 * given room-space pointer position, keeping the OPPOSITE corner fixed in
 * world space -- the same "planted corner" behavior as most Sims-style
 * placement tools. Handles rotation: the opposite corner is only truly
 * fixed in *room* space, which may not be axis-aligned with the drag.
 */
export function computeResizeFromHandle(obj, handle, pointerX, pointerY, { preserveAspect = false, minSize = MIN_OBJECT_SIZE } = {}) {
  const { sx, sy } = HANDLE_SIGN[handle];
  const anchorLocal = { lx: -sx * (obj.width / 2), ly: -sy * (obj.height / 2) };
  const anchorWorld = localToWorld(obj, anchorLocal.lx, anchorLocal.ly);

  const theta = toRad(obj.rotation || 0);
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  const worldDx = pointerX - anchorWorld.x;
  const worldDy = pointerY - anchorWorld.y;
  // R(-theta) applied to the world delta from the anchor -> local delta.
  const localDx = worldDx * cos + worldDy * sin;
  const localDy = -worldDx * sin + worldDy * cos;

  let newWidth = Math.max(minSize, sx * localDx);
  let newHeight = Math.max(minSize, sy * localDy);

  if (preserveAspect) {
    const scale = Math.max(newWidth / obj.width, newHeight / obj.height);
    newWidth = Math.max(minSize, obj.width * scale);
    newHeight = Math.max(minSize, obj.height * scale);
  }

  // The anchor corner's LOCAL coordinates at the new size (same sign,
  // scaled by the new half-width/height) rotate to the same fixed world
  // point (anchorWorld), which pins down the new center: newCenter =
  // anchorWorld - R(theta)*anchorLocalNew.
  const anchorLocalNew = { lx: -sx * (newWidth / 2), ly: -sy * (newHeight / 2) };
  const rotatedAnchorNew = {
    x: anchorLocalNew.lx * cos - anchorLocalNew.ly * sin,
    y: anchorLocalNew.lx * sin + anchorLocalNew.ly * cos,
  };
  const newCenter = {
    x: anchorWorld.x - rotatedAnchorNew.x,
    y: anchorWorld.y - rotatedAnchorNew.y,
  };

  return {
    x: newCenter.x - newWidth / 2,
    y: newCenter.y - newHeight / 2,
    width: newWidth,
    height: newHeight,
  };
}

/** Angle, in degrees, from (cx, cy) to (x, y). Screen convention: 0 = right, 90 = down. */
export function angleDegrees(cx, cy, x, y) {
  return (Math.atan2(y - cy, x - cx) * 180) / Math.PI;
}

/** Normalizes a degree value into [0, 360). */
function normalizeDegrees(deg) {
  return ((deg % 360) + 360) % 360;
}

/**
 * Live rotation for a toolbar-armed rotate-drag (§8.3): the object spins by
 * however much the pointer's angle (around the object's center) has changed
 * since the drag started, added to whatever rotation it started at -- so
 * grabbing anywhere on the canvas (not just a handle) tracks smoothly with
 * no jump to "point at the cursor" on the first movement.
 */
export function computeDragRotation(startRotationDeg, startAngleDeg, currentAngleDeg) {
  return normalizeDegrees(startRotationDeg + (currentAngleDeg - startAngleDeg));
}

// Object types with an existing non-spatial #configure-controls section
// (§8.4) -- mirrors the type list client/js/main.js's
// selectBuilderObjectForConfiguration already switches on.
const TUNE_ELIGIBLE_TYPES = new Set(['bookshelf', 'tv', 'music_player', 'ai_character', 'escape_door', 'hidden_item']);

/**
 * Which icons the floating selection toolbar shows for `objectType` (§8.1),
 * in display order. A locked or no-permission object (§8.5) is reduced to a
 * read-only `tune` ("View Details") if the type has a details section at
 * all, or to an empty toolbar if it doesn't -- there is nothing to view or
 * do on a locked plain table/chair/bar/sofa.
 */
export function toolbarIconsForObjectType(objectType, { isLocked = false, canEdit = true } = {}) {
  const hasTune = TUNE_ELIGIBLE_TYPES.has(objectType);
  if (isLocked || !canEdit) {
    return hasTune ? ['tune'] : [];
  }
  const icons = ['rotate_right', 'palette'];
  if (hasTune) icons.push('tune');
  icons.push('delete');
  return icons;
}
