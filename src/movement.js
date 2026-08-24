export const ROOM_BOUNDS = {
  width: 800,
  height: 600,
  minX: 20,
  minY: 20,
  maxX: 780,
  maxY: 580,
};

// Axis-aligned bounding boxes for impassable furniture.
// Each entry is { x, y, w, h } in room pixel coords.
// A player is treated as a point (their feet position).
export const OBSTACLES = [
  { id: 'sofa-left',    x:  48, y: 330, w: 166, h: 80  },  // left purple sofa
  { id: 'sofa-right',  x: 578, y: 330, w: 166, h: 80  },  // right pink sofa
  { id: 'table',       x: 348, y: 370, w: 104, h: 42  },  // coffee table
  { id: 'dj-deck',     x: 118, y: 430, w:  64, h: 46  },  // DJ deck
];

/**
 * Returns true if the point (px, py) is inside any obstacle rect (with margin).
 */
export function collidesWithObstacle(px, py, margin = 8) {
  for (const o of OBSTACLES) {
    if (
      px >= o.x - margin &&
      px <= o.x + o.w + margin &&
      py >= o.y - margin &&
      py <= o.y + o.h + margin
    ) return true;
  }
  return false;
}

/**
 * Given a desired position, slide it outside any overlapping obstacle.
 * Tries x-only and y-only slides as fallback (wall-slide behaviour).
 */
export function resolveCollision(current, desired) {
  if (!collidesWithObstacle(desired.x, desired.y)) return desired;
  // try x-slide
  const slideX = { x: desired.x, y: current.y };
  if (!collidesWithObstacle(slideX.x, slideX.y)) return clampPosition(slideX);
  // try y-slide
  const slideY = { x: current.x, y: desired.y };
  if (!collidesWithObstacle(slideY.x, slideY.y)) return clampPosition(slideY);
  // fully blocked
  return current;
}

export function createPosition(x, y) {
  return {
    x: x ?? ROOM_BOUNDS.width / 2,
    y: y ?? ROOM_BOUNDS.height / 2,
  };
}

export function calculateDistance(a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  return Math.sqrt(dx * dx + dy * dy);
}

export function moveToward(current, target, step) {
  const dist = calculateDistance(current, target);

  if (dist <= step) {
    return { x: target.x, y: target.y };
  }

  const ratio = step / dist;
  return {
    x: current.x + (target.x - current.x) * ratio,
    y: current.y + (target.y - current.y) * ratio,
  };
}

export function clampPosition(pos) {
  return {
    x: Math.max(ROOM_BOUNDS.minX, Math.min(ROOM_BOUNDS.maxX, pos.x)),
    y: Math.max(ROOM_BOUNDS.minY, Math.min(ROOM_BOUNDS.maxY, pos.y)),
  };
}

export function isWithinBounds(pos) {
  return (
    pos.x >= ROOM_BOUNDS.minX &&
    pos.x <= ROOM_BOUNDS.maxX &&
    pos.y >= ROOM_BOUNDS.minY &&
    pos.y <= ROOM_BOUNDS.maxY
  );
}
