import { resolveObjectColor, objectTypeIcon } from './builder-objects.js';
import { resolveRoomStyle, DEFAULT_ROOM_STYLE } from './room-styles.js';

const ROOM_WIDTH = 800;
const ROOM_HEIGHT = 600;
const WALL_HEIGHT = ROOM_HEIGHT * 0.42;
// Corner resize-handle square side length, in room-space pixels (§8.3).
// Matches the +4 outset the selection dashed outline already uses, so the
// handles sit right at the outline's corners.
const RESIZE_HANDLE_SIZE = 10;

// The Lobby keeps its own fixed, branded look regardless of the 5 selectable
// custom-room styles (its colors match what this file always rendered).
const LOBBY_STYLE = {
  backdropTop: '#2a2438',
  backdropBottom: '#1c1828',
  wallTop: '#4a3f5c',
  wallBottom: '#6e6082',
  floorLight: '#c9a87c',
  floorDark: '#b8956a',
  lightColor: '255, 200, 150',
};

let _animFrame = null;
let _canvas = null;
let _builderObjects = [];
let _isLobby = true;
let _roomStyleId = DEFAULT_ROOM_STYLE;
let _neighbors = { top: false, bottom: false, left: false, right: false };
let _selectedObjectId = null;

/** Draws the room. Pass `{ isLobby: false, roomStyle }` for custom/user-built rooms so they
 * start as an empty shell (walls/floor only, colored per the chosen style) instead of the
 * branded lobby furniture, ready to be furnished via the room builder. */
export function drawRoom(canvas, { isLobby = true, roomStyle = DEFAULT_ROOM_STYLE } = {}) {
  _canvas = canvas;
  _isLobby = isLobby;
  _roomStyleId = roomStyle;
  if (_animFrame) cancelAnimationFrame(_animFrame);
  _animLoop();
}

/** Updates whether the current room should render the fixed lobby ambient furniture. */
export function setRoomIsLobby(isLobby) {
  _isLobby = Boolean(isLobby);
}

/** Updates the active custom-room style (ignored while `isLobby` is true). */
export function setRoomStyle(roomStyle) {
  _roomStyleId = roomStyle;
}

/** Sets the builder-placed objects (for the player's current tile) to render on the canvas. */
export function setBuilderObjects(objects) {
  _builderObjects = Array.isArray(objects) ? objects : [];
}

/** Updates which of the current tile's 4 edges have a neighboring tile (design doc
 * feature_designs/build_mode_ui_redesign_feature_design.md §10.2/§10.3), driving whether
 * `drawWall`/`drawEdgeJambs` render a walkable doorway or a capped rail on each edge.
 * Pass the result of `neighborTileFlags(tiles, currentTile)` from world-map.js. */
export function setTileNeighbors(neighbors) {
  _neighbors = {
    top: Boolean(neighbors?.top),
    bottom: Boolean(neighbors?.bottom),
    left: Boolean(neighbors?.left),
    right: Boolean(neighbors?.right),
  };
}

/** Sets which builder object (by id) is currently selected in Build Mode (design doc
 * feature_designs/build_mode_ui_redesign_feature_design.md §8.1/§13), driving the
 * on-canvas selection highlight `drawBuilderObjects` draws around it. Pass `null` to
 * clear the selection (e.g. on Escape or after a delete). */
export function setSelectedBuilderObjectId(objectId) {
  _selectedObjectId = objectId || null;
}

/** Pure hit-test for the Build-Mode-only doorway/rail click shortcut (design doc
 * §10.4): given a click point in room coordinates (as returned by
 * `canvasToRoomCoords`), reports which of the 4 tile edges (if any) the point
 * falls within the doorway/rail hotspot of, and whether that edge currently has
 * a neighboring tile (`isOpen`). The hotspot rectangles intentionally match the
 * exact regions `drawTopDoorway`/`drawEdgeJambs` paint, regardless of whether
 * that edge is currently rendered open or closed, so a click always lands in
 * the same visual spot whether the edge is a doorway or a capped rail.
 * Callers are expected to only act on a closed (`isOpen: false`) hit -- an
 * open hit needs no special handling since the existing click-to-move flow
 * already walks the avatar there and crosses the tile transition naturally.
 * Returns `null` when the point isn't within any edge's hotspot. Pure
 * geometry, no canvas/DOM dependency, so it's directly unit-testable. */
export function edgeHotspotAtPoint(x, y, neighbors) {
  const n = {
    top: Boolean(neighbors?.top),
    bottom: Boolean(neighbors?.bottom),
    left: Boolean(neighbors?.left),
    right: Boolean(neighbors?.right),
  };

  const doorW = 130;
  const doorH = WALL_HEIGHT * 0.82;
  const doorX = ROOM_WIDTH / 2 - doorW / 2;
  const doorY = WALL_HEIGHT - doorH;
  if (x >= doorX && x <= doorX + doorW && y >= doorY && y <= doorY + doorH) {
    return { edge: 'top', isOpen: n.top };
  }

  const gap = 130;
  const jambStub = 40;
  const floorCenterY = WALL_HEIGHT + (ROOM_HEIGHT - WALL_HEIGHT) / 2;
  const y0 = floorCenterY - gap / 2;
  const y1 = floorCenterY + gap / 2;

  if (y >= ROOM_HEIGHT - jambStub && y <= ROOM_HEIGHT) {
    const x0 = ROOM_WIDTH / 2 - gap / 2;
    const x1 = ROOM_WIDTH / 2 + gap / 2;
    if (x >= x0 && x <= x1) return { edge: 'bottom', isOpen: n.bottom };
  }
  if (x >= 0 && x <= jambStub && y >= y0 && y <= y1) {
    return { edge: 'left', isOpen: n.left };
  }
  if (x >= ROOM_WIDTH - jambStub && x <= ROOM_WIDTH && y >= y0 && y <= y1) {
    return { edge: 'right', isOpen: n.right };
  }

  return null;
}

/** Determines which edge a player crossed when moving from `fromTile` to
 * `toTile` (adjacent tile coordinates, e.g. `{x:0,y:0}` -> `{x:0,y:-1}`),
 * so the caller can play a matching directional transition animation.
 * Returns null when the tiles are the same or not orthogonally adjacent
 * (nothing to animate). */
export function tileTransitionDirection(fromTile, toTile) {
  if (!fromTile || !toTile) return null;
  const dx = toTile.x - fromTile.x;
  const dy = toTile.y - fromTile.y;
  if (dx === 0 && dy === -1) return 'top';
  if (dx === 0 && dy === 1) return 'bottom';
  if (dx === -1 && dy === 0) return 'left';
  if (dx === 1 && dy === 0) return 'right';
  return null;
}


function _activeStyle() {
  return _isLobby ? LOBBY_STYLE : resolveRoomStyle(_roomStyleId);
}

function _animLoop() {
  const ctx = _canvas.getContext('2d');
  ctx.clearRect(0, 0, ROOM_WIDTH, ROOM_HEIGHT);

  drawBackdrop(ctx);
  drawWall(ctx);
  drawFloor(ctx);
  drawEdgeJambs(ctx);
  if (_isLobby) drawFurniture(ctx);
  drawBuilderObjects(ctx);
  drawAmbientLight(ctx);
  drawCeilingFixture(ctx, ROOM_WIDTH / 2, WALL_HEIGHT * 0.22);
  drawVignette(ctx);

  _animFrame = requestAnimationFrame(_animLoop);
}

function drawBackdrop(ctx) {
  const style = _activeStyle();
  const grad = ctx.createLinearGradient(0, 0, 0, ROOM_HEIGHT);
  grad.addColorStop(0, style.backdropTop);
  grad.addColorStop(1, style.backdropBottom);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, ROOM_WIDTH, ROOM_HEIGHT);
}

function drawWall(ctx) {
  const style = _activeStyle();
  const grad = ctx.createLinearGradient(0, 0, 0, WALL_HEIGHT);
  grad.addColorStop(0, style.wallTop);
  grad.addColorStop(1, style.wallBottom);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, ROOM_WIDTH, WALL_HEIGHT);

  // subtle vertical panel lines
  ctx.fillStyle = 'rgba(255,255,255,0.03)';
  for (let x = 0; x < ROOM_WIDTH; x += 80) {
    ctx.fillRect(x, 0, 1, WALL_HEIGHT);
  }

  drawWainscoting(ctx, style);

  drawWindow(ctx, ROOM_WIDTH * 0.08, ROOM_HEIGHT * 0.06, ROOM_WIDTH * 0.28, ROOM_HEIGHT * 0.22);
  drawWindow(ctx, ROOM_WIDTH * 0.64, ROOM_HEIGHT * 0.06, ROOM_WIDTH * 0.28, ROOM_HEIGHT * 0.22);

  drawWallArt(ctx, ROOM_WIDTH * 0.42, ROOM_HEIGHT * 0.08, 70, 50);

  // Skirting board: dark base, lit top edge, dark shadow line underneath.
  ctx.fillStyle = shadeColor(style.wallBottom, -28);
  ctx.fillRect(0, WALL_HEIGHT - 10, ROOM_WIDTH, 12);
  ctx.fillStyle = 'rgba(255,255,255,0.16)';
  ctx.fillRect(0, WALL_HEIGHT - 10, ROOM_WIDTH, 1.5);
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  ctx.fillRect(0, WALL_HEIGHT - 2, ROOM_WIDTH, 4);

  if (_neighbors.top) drawTopDoorway(ctx, style);
}

/** Cuts a walkable doorway opening into the top wall (design doc §10.3), used only when a
 * neighboring tile exists to the north. Replaces a section of the flat wall fill with the
 * backdrop color, a door-frame outline, and a pair of door-leaf graphics drawn ajar, all in
 * the room's current style colors -- purely decorative, never affects tile-transition collision. */
function drawTopDoorway(ctx, style) {
  const doorW = 130;
  const doorH = WALL_HEIGHT * 0.82;
  const doorX = ROOM_WIDTH / 2 - doorW / 2;
  const doorY = WALL_HEIGHT - doorH;

  // Opening: replaces the wall fill with the backdrop color so it reads as
  // a hole through to the next tile rather than a painted decal.
  ctx.fillStyle = style.backdropBottom;
  ctx.fillRect(doorX, doorY, doorW, doorH);

  // Frame outline.
  ctx.strokeStyle = shadeColor(style.wallBottom, -30);
  ctx.lineWidth = 6;
  ctx.strokeRect(doorX, doorY, doorW, doorH);

  // A pair of door leaves, hinged at the outer frame edges and drawn
  // swung open at an angle ("ajar") rather than flush across the opening.
  const leafW = doorW / 2 - 4;
  const leafH = doorH - 6;
  const swingAngle = 0.38; // radians, ~22°

  ctx.save();
  ctx.translate(doorX + 3, doorY + 3);
  ctx.rotate(swingAngle);
  ctx.fillStyle = style.wallBottom;
  ctx.fillRect(0, 0, leafW, leafH);
  ctx.fillStyle = 'rgba(255,255,255,0.14)';
  ctx.fillRect(2, 2, leafW - 4, 4);
  ctx.restore();

  ctx.save();
  ctx.translate(doorX + doorW - 3, doorY + 3);
  ctx.rotate(-swingAngle);
  ctx.fillStyle = style.wallBottom;
  ctx.fillRect(-leafW, 0, leafW, leafH);
  ctx.fillStyle = 'rgba(255,255,255,0.14)';
  ctx.fillRect(-leafW + 2, 2, leafW - 4, 4);
  ctx.restore();
}

/** Left/right/bottom edge "jambs" (design doc §10.3). These three edges have no wall at
 * all today, so this adds short partial trim framing each edge: where a neighbor tile
 * exists, the gap gets a floor threshold strip (walk-through signal); where it doesn't,
 * the gap closes into a short skirting-style rail stub (dead-end signal). Purely
 * decorative, never affects tile-transition collision. */
function drawEdgeJambs(ctx) {
  const style = _activeStyle();
  const gap = 130;
  const jambDepth = 14;
  const jambStub = 40;

  // Bottom edge: horizontal, gap centered on the room's width.
  {
    const x0 = ROOM_WIDTH / 2 - gap / 2;
    const x1 = ROOM_WIDTH / 2 + gap / 2;
    drawJambPost(ctx, x0 - jambDepth, ROOM_HEIGHT - jambStub, jambDepth, jambStub, style);
    drawJambPost(ctx, x1, ROOM_HEIGHT - jambStub, jambDepth, jambStub, style);
    if (_neighbors.bottom) {
      ctx.fillStyle = style.floorDark;
      ctx.fillRect(x0, ROOM_HEIGHT - jambDepth, gap, jambDepth);
    } else {
      drawSkirtingRail(ctx, x0, ROOM_HEIGHT - 10, gap, 'horizontal', style);
    }
  }

  // Left/right edges: vertical, gap centered on the floor's vertical span.
  const floorCenterY = WALL_HEIGHT + (ROOM_HEIGHT - WALL_HEIGHT) / 2;
  const y0 = floorCenterY - gap / 2;
  const y1 = floorCenterY + gap / 2;

  drawJambPost(ctx, 0, y0 - jambDepth, jambStub, jambDepth, style);
  drawJambPost(ctx, 0, y1, jambStub, jambDepth, style);
  if (_neighbors.left) {
    ctx.fillStyle = style.floorDark;
    ctx.fillRect(0, y0, jambDepth, gap);
  } else {
    drawSkirtingRail(ctx, 4, y0, gap, 'vertical', style);
  }

  drawJambPost(ctx, ROOM_WIDTH - jambStub, y0 - jambDepth, jambStub, jambDepth, style);
  drawJambPost(ctx, ROOM_WIDTH - jambStub, y1, jambStub, jambDepth, style);
  if (_neighbors.right) {
    ctx.fillStyle = style.floorDark;
    ctx.fillRect(ROOM_WIDTH - jambDepth, y0, jambDepth, gap);
  } else {
    drawSkirtingRail(ctx, ROOM_WIDTH - 4 - gap, y0, gap, 'vertical', style);
  }
}

/** A short solid wall-trim stub framing one side of an edge opening. */
function drawJambPost(ctx, x, y, w, h, style) {
  ctx.fillStyle = style.wallBottom;
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = 'rgba(0,0,0,0.25)';
  ctx.fillRect(x, y, w, 2);
}

/** A closed-edge rail/skirting stub (dead-end signal), echoing the existing top-wall
 * skirting-board treatment: dark base, lit top edge, dark shadow line. */
function drawSkirtingRail(ctx, x, y, length, orientation, style) {
  const thickness = 10;
  const w = orientation === 'horizontal' ? length : thickness;
  const h = orientation === 'horizontal' ? thickness : length;

  ctx.fillStyle = shadeColor(style.wallBottom, -28);
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = 'rgba(255,255,255,0.16)';
  if (orientation === 'horizontal') ctx.fillRect(x, y, w, 1.5);
  else ctx.fillRect(x, y, 1.5, h);
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  if (orientation === 'horizontal') ctx.fillRect(x, y + h - 2, w, 2);
  else ctx.fillRect(x + w - 2, y, 2, h);
}

/** Panelled lower wall (wainscoting) with a dado rail. Breaks up the flat
 * wall gradient and gives the room a furnished, hotel-lobby feel instead of
 * a plain painted box. Purely decorative — no effect on collision. */
function drawWainscoting(ctx, style) {
  const railY = WALL_HEIGHT * 0.62;

  // Lower section reads slightly darker than the wall above the rail.
  ctx.fillStyle = 'rgba(0,0,0,0.13)';
  ctx.fillRect(0, railY, ROOM_WIDTH, WALL_HEIGHT - railY);

  // Recessed rectangular panels along the lower wall.
  const panelW = 92;
  const panelTop = railY + 13;
  const panelH = WALL_HEIGHT - railY - 27;
  if (panelH > 6) {
    for (let x = 16; x + panelW < ROOM_WIDTH; x += panelW + 16) {
      ctx.fillStyle = 'rgba(0,0,0,0.15)';
      ctx.beginPath();
      ctx.roundRect(x, panelTop, panelW, panelH, 3);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.07)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(x + 1, panelTop + 1, panelW - 2, panelH - 2, 3);
      ctx.stroke();
    }
  }

  // Dado rail: body, lit top edge, cast shadow beneath.
  ctx.fillStyle = shadeColor(style.wallBottom, 16);
  ctx.fillRect(0, railY - 5, ROOM_WIDTH, 6);
  ctx.fillStyle = 'rgba(255,255,255,0.18)';
  ctx.fillRect(0, railY - 5, ROOM_WIDTH, 1.5);
  ctx.fillStyle = 'rgba(0,0,0,0.2)';
  ctx.fillRect(0, railY + 1, ROOM_WIDTH, 2.5);
}

function drawWindow(ctx, x, y, w, h) {
  ctx.fillStyle = '#3d2f54';
  ctx.fillRect(x - 4, y - 4, w + 8, h + 8);
  ctx.fillStyle = '#2a2040';
  ctx.fillRect(x, y, w, h);

  // warm daytime window
  const skyGrad = ctx.createLinearGradient(x, y, x, y + h);
  skyGrad.addColorStop(0, '#87ceeb');
  skyGrad.addColorStop(0.6, '#b8dff5');
  skyGrad.addColorStop(1, '#fde9c4');
  ctx.fillStyle = skyGrad;
  ctx.fillRect(x + 4, y + 4, w - 8, h - 8);

  // a few clouds / birds
  ctx.fillStyle = 'rgba(255,255,255,0.55)';
  ctx.beginPath(); ctx.ellipse(x + 30, y + 14, 14, 6, 0, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.ellipse(x + 42, y + 11, 10, 5, 0, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.ellipse(x + w - 30, y + 22, 11, 5, 0, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.ellipse(x + w - 20, y + 19, 8, 4, 0, 0, Math.PI * 2); ctx.fill();

  ctx.strokeStyle = '#3d2f54';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(x + w / 2, y);
  ctx.lineTo(x + w / 2, y + h);
  ctx.moveTo(x, y + h / 2);
  ctx.lineTo(x + w, y + h / 2);
  ctx.stroke();

  ctx.fillStyle = 'rgba(255, 200, 100, 0.08)';
  ctx.fillRect(x + 4, y + 4, w - 8, h - 8);
}

function drawWallArt(ctx, x, y, w, h) {
  // simple framed painting — warm abstract
  ctx.fillStyle = '#1e1a2a';
  ctx.fillRect(x - 5, y - 5, w + 10, h + 10);
  ctx.fillStyle = '#f5e6c8';
  ctx.fillRect(x, y, w, h);
  // abstract strokes
  ctx.strokeStyle = '#e07a5f'; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(x + 8, y + h - 10); ctx.bezierCurveTo(x + 20, y + 8, x + 50, y + h - 8, x + w - 8, y + 12); ctx.stroke();
  ctx.strokeStyle = '#3d405b'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(x + 12, y + 20); ctx.lineTo(x + w - 12, y + h - 20); ctx.stroke();
  ctx.strokeStyle = '#81b29a'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.arc(x + w * 0.65, y + h * 0.4, 8, 0, Math.PI * 2); ctx.stroke();
}

function drawFloor(ctx) {
  const floorY = WALL_HEIGHT;
  const tileW = 50;
  const tileH = 25;
  const style = _activeStyle();

  for (let row = 0; row < 12; row++) {
    for (let col = 0; col < 18; col++) {
      const x = col * tileW + (row % 2 ? tileW / 2 : 0);
      const y = floorY + row * tileH;
      const shade = (row + col) % 2 === 0 ? style.floorLight : style.floorDark;
      ctx.fillStyle = shade;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + tileW, y);
      ctx.lineTo(x + tileW + tileW * 0.15, y + tileH);
      ctx.lineTo(x + tileW * 0.15, y + tileH);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = 'rgba(0,0,0,0.06)';
      ctx.stroke();
    }
  }

  drawFloorDepth(ctx);

  if (!_isLobby) return;

  const rugX = ROOM_WIDTH * 0.32;
  const rugY = ROOM_HEIGHT * 0.58;
  ctx.fillStyle = 'rgba(139, 69, 100, 0.7)';
  ctx.beginPath();
  ctx.ellipse(rugX + 90, rugY + 40, 110, 65, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = 'rgba(192, 132, 252, 0.5)';
  ctx.beginPath();
  ctx.ellipse(rugX + 90, rugY + 40, 85, 50, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255, 107, 157, 0.4)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.ellipse(rugX + 90, rugY + 40, 95, 55, 0, 0, Math.PI * 2);
  ctx.stroke();
}

function drawFurniture(ctx) {
  const sofaY = ROOM_HEIGHT * 0.58;
  const tableY = ROOM_HEIGHT * 0.62;
  const deckY = ROOM_HEIGHT * 0.72;

  // Contact shadows are drawn first, so every piece visually sits ON the
  // floor instead of hovering above it.
  drawContactShadow(ctx, 125, sofaY + 62, 88, 15);
  drawContactShadow(ctx, ROOM_WIDTH - 145, sofaY + 62, 88, 15);
  drawContactShadow(ctx, 34, WALL_HEIGHT + 39, 28, 9);
  drawContactShadow(ctx, ROOM_WIDTH - 41, WALL_HEIGHT + 39, 28, 9);
  drawContactShadow(ctx, ROOM_WIDTH / 2, tableY + 40, 60, 12);
  drawContactShadow(ctx, ROOM_WIDTH * 0.15 + 30, deckY + 42, 40, 10);

  drawSofa(ctx, 60, sofaY, '#5b4a8a');       // muted indigo
  drawSofa(ctx, ROOM_WIDTH - 210, sofaY, '#7a4060');  // muted rose
  drawPlant(ctx, 20, WALL_HEIGHT - 10);
  drawPlant(ctx, ROOM_WIDTH - 55, WALL_HEIGHT - 10);
  drawCoffeeTable(ctx, ROOM_WIDTH / 2 - 50, tableY);
  drawNeonSign(ctx, ROOM_WIDTH / 2, WALL_HEIGHT - 30);
  drawDJDeck(ctx, ROOM_WIDTH * 0.15, deckY);
}

function drawSofa(ctx, x, y, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(x, y, 130, 45, 8);
  ctx.fill();
  ctx.fillStyle = shadeColor(color, -20);
  ctx.fillRect(x - 12, y + 5, 18, 55);
  ctx.fillRect(x + 124, y + 5, 18, 55);
  ctx.fillStyle = shadeColor(color, 15);
  ctx.beginPath();
  ctx.roundRect(x + 5, y - 18, 120, 22, 6);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.1)';
  ctx.beginPath();
  ctx.roundRect(x + 10, y + 5, 110, 30, 4);
  ctx.fill();
}

function drawPlant(ctx, x, y) {
  ctx.fillStyle = '#8b4513';
  ctx.beginPath();
  ctx.roundRect(x, y + 15, 28, 32, 4);
  ctx.fill();
  const greens = ['#22c55e', '#16a34a', '#4ade80', '#15803d'];
  for (let i = 0; i < 6; i++) {
    const angle = (i / 6) * Math.PI * 2 - Math.PI / 2;
    ctx.fillStyle = greens[i % greens.length];
    ctx.beginPath();
    ctx.ellipse(
      x + 14 + Math.cos(angle) * 14,
      y + 5 + Math.sin(angle) * 8,
      14, 20, angle, 0, Math.PI * 2
    );
    ctx.fill();
  }
}

function drawCoffeeTable(ctx, x, y) {
  // Table surface + legs
  ctx.fillStyle = '#92400e';
  ctx.fillRect(x, y, 100, 10);
  ctx.fillRect(x + 8, y + 10, 8, 28);
  ctx.fillRect(x + 84, y + 10, 8, 28);

  // Small plant/vase on table
  ctx.fillStyle = '#fef3c7';
  ctx.beginPath();
  ctx.arc(x + 50, y - 3, 10, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#78350f';
  ctx.beginPath();
  ctx.ellipse(x + 50, y - 3, 8, 3, 0, 0, Math.PI * 2);
  ctx.fill();

  // Coffee cups
  const cups = [
    { cx: x + 22, cy: y - 1 },
    { cx: x + 76, cy: y - 1 },
  ];
  for (const { cx, cy } of cups) {
    // Saucer
    ctx.fillStyle = '#d4c9b8';
    ctx.beginPath();
    ctx.ellipse(cx, cy + 3, 8, 2.5, 0, 0, Math.PI * 2);
    ctx.fill();
    // Cup body
    ctx.fillStyle = '#f0ebe0';
    ctx.beginPath();
    ctx.roundRect(cx - 5.5, cy - 8, 11, 10, 2);
    ctx.fill();
    // Coffee surface
    ctx.fillStyle = '#5b2d0a';
    ctx.beginPath();
    ctx.ellipse(cx, cy - 7, 4.5, 2, 0, 0, Math.PI * 2);
    ctx.fill();
    // Handle
    ctx.strokeStyle = '#d0c8b8';
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    ctx.arc(cx + 6.5, cy - 3, 3.5, -Math.PI * 0.55, Math.PI * 0.55);
    ctx.stroke();
    // Steam
    ctx.strokeStyle = 'rgba(255,255,255,0.28)';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(cx - 2, cy - 10);
    ctx.bezierCurveTo(cx - 4, cy - 14, cx, cy - 14, cx - 2, cy - 18);
    ctx.stroke();
  }
}

function drawNeonSign(ctx, x, y) {
  const t = performance.now() / 1600;
  const pulse = 0.82 + 0.18 * Math.sin(t);

  ctx.font = 'bold 17px Fredoka, sans-serif';
  ctx.textAlign = 'center';
  ctx.shadowColor = 'rgba(192,132,252,0.6)';
  ctx.shadowBlur = 12 * pulse;
  ctx.fillStyle = `rgba(230,210,255,${0.78 + 0.14 * pulse})`;
  ctx.fillText('✦ OMNILAUNGE ✦', x, y);
  ctx.shadowBlur = 0;
}

function drawDiscoBall(ctx, x, y) {
  const t = performance.now() / 600;
  const r = 18;

  // Hanging wire
  ctx.strokeStyle = 'rgba(180,180,200,0.45)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, y - r);
  ctx.stroke();

  // Ball body
  const ballGrad = ctx.createRadialGradient(x - 4, y - 4, 2, x, y, r);
  ballGrad.addColorStop(0, '#e0e8ff');
  ballGrad.addColorStop(0.5, '#8899bb');
  ballGrad.addColorStop(1, '#334466');
  ctx.fillStyle = ballGrad;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();

  // Mosaic tiles
  const numCols = 8;
  const numRows = 5;
  const tileColors = ['#ff6b9d', '#c084fc', '#67e8f9', '#fbbf24', '#4ade80', '#fb7185', '#a78bfa', '#38bdf8'];
  for (let row = 0; row < numRows; row++) {
    for (let col = 0; col < numCols; col++) {
      const theta = (col / numCols) * Math.PI * 2 + t;
      const phi = ((row + 1) / (numRows + 1)) * Math.PI;
      const tx = x + r * 0.85 * Math.sin(phi) * Math.cos(theta);
      const ty = y + r * 0.85 * (Math.cos(phi) * 0.6 + Math.sin(phi) * 0.3);
      const size = 2.5;
      ctx.fillStyle = tileColors[(row * numCols + col) % tileColors.length];
      ctx.globalAlpha = 0.7 + 0.3 * Math.sin(t + row + col);
      ctx.fillRect(tx - size / 2, ty - size / 2, size, size);
    }
  }
  ctx.globalAlpha = 1;

  // Rotating spotlight beams — subtle, no colour cycling
  const numBeams = 4;
  for (let i = 0; i < numBeams; i++) {
    const angle = t * 0.7 + (i / numBeams) * Math.PI * 2;
    const beamLen = 140 + 25 * Math.sin(t + i);
    const bx = x + Math.cos(angle) * beamLen;
    const by = y + Math.sin(angle) * beamLen * 0.45 + 70;
    const grad = ctx.createRadialGradient(bx, by, 0, bx, by, 16);
    grad.addColorStop(0, 'rgba(255,255,220,0.12)');
    grad.addColorStop(1, 'transparent');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(bx, by, 16, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawDJDeck(ctx, x, y) {
  ctx.fillStyle = '#374151';
  ctx.fillRect(x, y, 60, 40);
  ctx.fillStyle = '#1f2937';
  ctx.beginPath();
  ctx.arc(x + 20, y + 20, 12, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x + 42, y + 20, 12, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#6b7280';
  ctx.beginPath();
  ctx.arc(x + 20, y + 20, 4, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x + 42, y + 20, 4, 0, Math.PI * 2);
  ctx.fill();
}

function drawAmbientLight(ctx) {
  const style = _activeStyle();
  const tint = style.lightColor || '255, 200, 150';
  const lampX = ROOM_WIDTH / 2;
  const lampY = WALL_HEIGHT;
  const grad = ctx.createRadialGradient(lampX, lampY, 10, lampX, lampY + 100, 280);
  grad.addColorStop(0, `rgba(${tint}, 0.12)`);
  grad.addColorStop(1, `rgba(${tint}, 0)`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, WALL_HEIGHT, ROOM_WIDTH, ROOM_HEIGHT - WALL_HEIGHT);
}

/** Picks the room's ceiling fixture: the Lobby keeps its spinning disco ball
 * (it's the branded club look, alongside its neon sign and DJ deck), while
 * each selectable custom-room style gets its OWN fixture and light tint so
 * every room doesn't look like the same nightclub. Purely decorative. */
function drawCeilingFixture(ctx, x, y) {
  if (_isLobby) {
    drawDiscoBall(ctx, x, y);
    return;
  }
  switch (_roomStyleId) {
    case 'cozy-den':
      drawLantern(ctx, x, y);
      return;
    case 'sunlit-studio':
      drawSkylight(ctx, x, y);
      return;
    case 'midnight-lounge':
      drawChandelierOrb(ctx, x, y);
      return;
    case 'minimalist-white':
      drawPendantSphere(ctx, x, y);
      return;
    case 'beach-cabana':
      drawCabanaLantern(ctx, x, y);
      return;
    case 'retro-arcade':
      drawNeonRing(ctx, x, y);
      return;
    case 'enchanted-garden':
      drawFairyLights(ctx, x, y);
      return;
    case 'modern-loft':
    default:
      drawPendantLamp(ctx, x, y);
  }
}

/** Modern Loft: an industrial cone-shade pendant lamp on a bare cord. */
function drawPendantLamp(ctx, x, y) {
  ctx.strokeStyle = 'rgba(20,20,24,0.7)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, y - 6);
  ctx.stroke();

  // Cone shade
  ctx.fillStyle = '#23262b';
  ctx.beginPath();
  ctx.moveTo(x - 4, y - 6);
  ctx.lineTo(x + 4, y - 6);
  ctx.lineTo(x + 22, y + 14);
  ctx.lineTo(x - 22, y + 14);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.12)';
  ctx.beginPath();
  ctx.moveTo(x - 4, y - 6);
  ctx.lineTo(x - 1, y - 6);
  ctx.lineTo(x - 10, y + 14);
  ctx.lineTo(x - 18, y + 14);
  ctx.closePath();
  ctx.fill();

  // Warm bulb glow, softly breathing
  const t = performance.now() / 2200;
  const pulse = 0.85 + 0.15 * Math.sin(t);
  const glow = ctx.createRadialGradient(x, y + 16, 2, x, y + 16, 60);
  glow.addColorStop(0, `rgba(210,225,255,${0.55 * pulse})`);
  glow.addColorStop(1, 'rgba(210,225,255,0)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(x, y + 16, 60, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = `rgba(240,245,255,${pulse})`;
  ctx.beginPath();
  ctx.arc(x, y + 16, 4, 0, Math.PI * 2);
  ctx.fill();
}

/** Cozy Den: a small hanging lantern with a warm, gently flickering candle glow. */
function drawLantern(ctx, x, y) {
  ctx.strokeStyle = 'rgba(60,40,25,0.7)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, y - 12);
  ctx.stroke();

  const t = performance.now() / 500;
  const flicker = 0.85 + 0.15 * Math.sin(t * 1.7) + 0.05 * Math.sin(t * 4.3);

  // Warm flame-lit glow behind the frame
  const glow = ctx.createRadialGradient(x, y, 2, x, y, 55);
  glow.addColorStop(0, `rgba(255,190,110,${0.5 * flicker})`);
  glow.addColorStop(1, 'rgba(255,190,110,0)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(x, y, 55, 0, Math.PI * 2);
  ctx.fill();

  // Wood-framed glass box
  ctx.fillStyle = '#4a3018';
  ctx.beginPath();
  ctx.roundRect(x - 13, y - 12, 26, 26, 3);
  ctx.fill();
  ctx.fillStyle = `rgba(255,205,130,${0.7 * flicker})`;
  ctx.beginPath();
  ctx.roundRect(x - 9, y - 8, 18, 18, 2);
  ctx.fill();
  ctx.strokeStyle = '#3a2412';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, y - 8); ctx.lineTo(x, y + 10);
  ctx.moveTo(x - 9, y + 1); ctx.lineTo(x + 9, y + 1);
  ctx.stroke();
  ctx.fillStyle = '#2f1d0d';
  ctx.fillRect(x - 15, y + 12, 30, 4);
}

/** Sunlit Studio: a bright recessed ceiling skylight instead of a hanging
 * fixture, casting soft daylight down into the room. */
function drawSkylight(ctx, x, y) {
  const w = 100;
  const h = 46;

  ctx.fillStyle = 'rgba(40,32,20,0.25)';
  ctx.fillRect(x - w / 2 - 4, y - h / 2 - 4, w + 8, h + 8);

  const sky = ctx.createLinearGradient(0, y - h / 2, 0, y + h / 2);
  sky.addColorStop(0, '#fff8e8');
  sky.addColorStop(1, '#ffe9b8');
  ctx.fillStyle = sky;
  ctx.fillRect(x - w / 2, y - h / 2, w, h);

  ctx.strokeStyle = 'rgba(120,100,70,0.55)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x - w / 6, y - h / 2); ctx.lineTo(x - w / 6, y + h / 2);
  ctx.moveTo(x + w / 6, y - h / 2); ctx.lineTo(x + w / 6, y + h / 2);
  ctx.stroke();

  // Soft light rays falling into the room
  const t = performance.now() / 3000;
  const shimmer = 0.5 + 0.15 * Math.sin(t);
  const rays = ctx.createRadialGradient(x, y + h / 2, 4, x, y + h / 2, 120);
  rays.addColorStop(0, `rgba(255,246,214,${0.4 * shimmer})`);
  rays.addColorStop(1, 'rgba(255,246,214,0)');
  ctx.fillStyle = rays;
  ctx.beginPath();
  ctx.arc(x, y + h / 2, 120, 0, Math.PI * 2);
  ctx.fill();
}

/** Midnight Lounge: a small, moody pendant orb with a slow violet pulse —
 * elegant ambience rather than a spinning mirror ball. */
function drawChandelierOrb(ctx, x, y) {
  ctx.strokeStyle = 'rgba(180,160,220,0.4)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, y - 10);
  ctx.stroke();

  const t = performance.now() / 1400;
  const pulse = 0.75 + 0.25 * Math.sin(t);

  const glow = ctx.createRadialGradient(x, y, 2, x, y, 70);
  glow.addColorStop(0, `rgba(180,140,255,${0.4 * pulse})`);
  glow.addColorStop(1, 'rgba(180,140,255,0)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(x, y, 70, 0, Math.PI * 2);
  ctx.fill();

  const orb = ctx.createRadialGradient(x - 4, y - 4, 1, x, y, 14);
  orb.addColorStop(0, '#efe6ff');
  orb.addColorStop(0.55, '#9b7fd6');
  orb.addColorStop(1, '#4b3477');
  ctx.fillStyle = orb;
  ctx.beginPath();
  ctx.arc(x, y, 14, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = `rgba(220,200,255,${0.5 * pulse})`;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(x, y, 20, 0, Math.PI * 2);
  ctx.stroke();
}

/** Minimalist White: a plain matte-white sphere pendant on a thin cord. */
function drawPendantSphere(ctx, x, y) {
  ctx.strokeStyle = 'rgba(120,120,120,0.5)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, y - 12);
  ctx.stroke();

  const t = performance.now() / 2600;
  const pulse = 0.85 + 0.15 * Math.sin(t);

  const glow = ctx.createRadialGradient(x, y, 2, x, y, 50);
  glow.addColorStop(0, `rgba(255,255,255,${0.35 * pulse})`);
  glow.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(x, y, 50, 0, Math.PI * 2);
  ctx.fill();

  const orb = ctx.createRadialGradient(x - 3, y - 3, 1, x, y, 12);
  orb.addColorStop(0, '#ffffff');
  orb.addColorStop(1, '#c8c8cc');
  ctx.fillStyle = orb;
  ctx.beginPath();
  ctx.arc(x, y, 12, 0, Math.PI * 2);
  ctx.fill();
}

/** Beach Cabana: a woven straw lantern casting a warm, gently swaying tropical glow. */
function drawCabanaLantern(ctx, x, y) {
  const t = performance.now() / 900;
  const sway = Math.sin(t * 0.6) * 3;

  ctx.strokeStyle = 'rgba(90,70,40,0.55)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x + sway, y - 14);
  ctx.stroke();

  const glowPulse = 0.85 + 0.15 * Math.sin(t * 1.3);
  const glow = ctx.createRadialGradient(x + sway, y, 2, x + sway, y, 60);
  glow.addColorStop(0, `rgba(255,220,150,${0.5 * glowPulse})`);
  glow.addColorStop(1, 'rgba(255,220,150,0)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(x + sway, y, 60, 0, Math.PI * 2);
  ctx.fill();

  // Woven straw body — a bulging barrel shape made of horizontal bands.
  ctx.fillStyle = '#c9995c';
  ctx.beginPath();
  ctx.moveTo(x + sway - 12, y - 14);
  ctx.quadraticCurveTo(x + sway - 18, y, x + sway - 12, y + 14);
  ctx.lineTo(x + sway + 12, y + 14);
  ctx.quadraticCurveTo(x + sway + 18, y, x + sway + 12, y - 14);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = 'rgba(120,80,40,0.5)';
  ctx.lineWidth = 1;
  for (let band = -8; band <= 8; band += 5) {
    ctx.beginPath();
    ctx.moveTo(x + sway - 14, y + band);
    ctx.lineTo(x + sway + 14, y + band);
    ctx.stroke();
  }
  ctx.fillStyle = `rgba(255,230,180,${0.6 * glowPulse})`;
  ctx.beginPath();
  ctx.arc(x + sway, y, 6, 0, Math.PI * 2);
  ctx.fill();
}

/** Retro Arcade: a glowing neon tube ring, alternating magenta/cyan like a
 * cabinet's marquee light. */
function drawNeonRing(ctx, x, y) {
  const t = performance.now() / 700;
  const pulse = 0.75 + 0.25 * Math.sin(t * 1.8);
  const hueShift = Math.sin(t * 0.5);
  const color = hueShift > 0 ? '255, 60, 220' : '80, 230, 255';

  const glow = ctx.createRadialGradient(x, y, 4, x, y, 65);
  glow.addColorStop(0, `rgba(${color}, ${0.45 * pulse})`);
  glow.addColorStop(1, `rgba(${color}, 0)`);
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(x, y, 65, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = `rgba(${color}, ${0.9 * pulse})`;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(x, y, 16, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeStyle = `rgba(255,255,255,${0.6 * pulse})`;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(x, y, 16, 0, Math.PI * 2);
  ctx.stroke();

  ctx.strokeStyle = 'rgba(20,10,30,0.6)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, y - 16);
  ctx.stroke();
}

/** Enchanted Garden: a small cluster of soft glowing fairy-light orbs
 * drifting gently, like fireflies caught under the canopy. */
function drawFairyLights(ctx, x, y) {
  const t = performance.now() / 1000;
  const positions = [
    { dx: -22, dy: -6, phase: 0 },
    { dx: -6, dy: 8, phase: 1.1 },
    { dx: 10, dy: -4, phase: 2.2 },
    { dx: 24, dy: 6, phase: 3.3 },
  ];

  ctx.strokeStyle = 'rgba(90,120,80,0.4)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x - 26, 0);
  ctx.quadraticCurveTo(x, y - 6, x + 26, 0);
  ctx.stroke();

  for (const p of positions) {
    const twinkle = 0.55 + 0.45 * Math.sin(t * 1.6 + p.phase);
    const lx = x + p.dx;
    const ly = y + p.dy;
    const glow = ctx.createRadialGradient(lx, ly, 1, lx, ly, 26);
    glow.addColorStop(0, `rgba(210,255,190,${0.5 * twinkle})`);
    glow.addColorStop(1, 'rgba(210,255,190,0)');
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(lx, ly, 26, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = `rgba(255,255,240,${0.7 + 0.3 * twinkle})`;
    ctx.beginPath();
    ctx.arc(lx, ly, 3, 0, Math.PI * 2);
    ctx.fill();
  }
}

/** Vertical linear gradient between two shades, in the CURRENT transform's
 * local space — so sprite helpers can call it after ctx.translate/rotate. */
function _vGrad(ctx, y0, y1, top, bottom) {
  const grad = ctx.createLinearGradient(0, y0, 0, y1);
  grad.addColorStop(0, top);
  grad.addColorStop(1, bottom);
  return grad;
}

/** Three-stop vertical gradient with a bright specular band near the top.
 * Two-stop ramps read as flat-shaded cardboard; the extra band is what makes
 * a surface look like a *material* catching the room's ceiling light. */
function _matGrad(ctx, y0, y1, color, { lit = 34, base = 0, dark = -30, bandAt = 0.22 } = {}) {
  const grad = ctx.createLinearGradient(0, y0, 0, y1);
  grad.addColorStop(0, shadeColor(color, lit));
  grad.addColorStop(bandAt, shadeColor(color, lit + 14));
  grad.addColorStop(0.62, shadeColor(color, base));
  grad.addColorStop(1, shadeColor(color, dark));
  return grad;
}

/** Wood-grain striations across a horizontal panel. Cheap (a handful of
 * low-alpha strokes) but it is the single biggest cue separating "a brown
 * rounded rectangle" from "a wooden table top". */
function _woodGrain(ctx, x, y, w, h, lines = 3) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();
  ctx.lineWidth = Math.max(0.5, h * 0.06);
  for (let i = 0; i < lines; i += 1) {
    const t = (i + 1) / (lines + 1);
    const gy = y + h * t;
    const bow = h * (i % 2 === 0 ? 0.22 : -0.18);
    ctx.strokeStyle = i % 2 === 0 ? 'rgba(0,0,0,0.13)' : 'rgba(255,255,255,0.09)';
    ctx.beginPath();
    ctx.moveTo(x, gy);
    ctx.quadraticCurveTo(x + w * 0.5, gy + bow, x + w, gy);
    ctx.stroke();
  }
  ctx.restore();
}

/** Ambient occlusion tucked under an overhanging edge (a table top over its
 * legs, a seat over its base). Contact points that stay fully lit are what
 * make furniture look pasted together out of separate shapes. */
function _underShade(ctx, x, y, w, depth) {
  const grad = ctx.createLinearGradient(0, y, 0, y + depth);
  grad.addColorStop(0, 'rgba(0,0,0,0.32)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(x, y, w, depth);
}

/** Soft elliptical contact shadow used to visually "plant" furniture and
 * props on the floor. Without one, sprites read as floating cutouts however
 * nicely they're shaded. `cy` should be the object's BASE (its lowest edge),
 * not its centre. */
function drawContactShadow(ctx, cx, cy, rx, ry, alpha = 0.36) {
  const r = Math.max(rx, 0.001);
  const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
  grad.addColorStop(0, `rgba(0,0,0,${alpha})`);
  grad.addColorStop(0.55, `rgba(0,0,0,${alpha * 0.42})`);
  grad.addColorStop(1, 'rgba(0,0,0,0)');

  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(1, ry / r); // squash the circle into the floor's perspective
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

/** Overlays distance shading and an ambient-occlusion band where the wall
 * meets the floor, so the flat tile grid reads as a lit surface receding
 * into the room rather than a flat checkerboard. */
function drawFloorDepth(ctx) {
  const floorY = WALL_HEIGHT;
  const floorH = ROOM_HEIGHT - floorY;

  // Ambient occlusion along the wall/floor seam.
  const ao = ctx.createLinearGradient(0, floorY, 0, floorY + 48);
  ao.addColorStop(0, 'rgba(0,0,0,0.40)');
  ao.addColorStop(0.5, 'rgba(0,0,0,0.13)');
  ao.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = ao;
  ctx.fillRect(0, floorY, ROOM_WIDTH, 48);

  // Warm pool of light in the middle of the floor, falling off to the edges.
  const sheen = ctx.createRadialGradient(
    ROOM_WIDTH / 2, floorY + floorH * 0.42, 20,
    ROOM_WIDTH / 2, floorY + floorH * 0.42, ROOM_WIDTH * 0.6,
  );
  sheen.addColorStop(0, 'rgba(255,242,218,0.13)');
  sheen.addColorStop(0.6, 'rgba(255,236,206,0.04)');
  sheen.addColorStop(1, 'rgba(0,0,0,0.15)');
  ctx.fillStyle = sheen;
  ctx.fillRect(0, floorY, ROOM_WIDTH, floorH);
}

/** Cinematic edge darkening that pulls the eye toward the centre of the room.
 * Drawn last so it sits over furniture and the disco lights alike. */
function drawVignette(ctx) {
  const grad = ctx.createRadialGradient(
    ROOM_WIDTH / 2, ROOM_HEIGHT * 0.5, ROOM_HEIGHT * 0.36,
    ROOM_WIDTH / 2, ROOM_HEIGHT * 0.5, ROOM_HEIGHT * 0.95,
  );
  grad.addColorStop(0, 'rgba(0,0,0,0)');
  grad.addColorStop(1, 'rgba(10,5,22,0.40)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, ROOM_WIDTH, ROOM_HEIGHT);
}

function shadeColor(hex, amount) {
  const num = parseInt(hex.replace('#', ''), 16);
  const r = Math.min(255, Math.max(0, (num >> 16) + amount));
  const g = Math.min(255, Math.max(0, ((num >> 8) & 0xff) + amount));
  const b = Math.min(255, Math.max(0, (num & 0xff) + amount));
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`;
}

export function canvasToRoomCoords(canvas, clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = ROOM_WIDTH / rect.width;
  const scaleY = ROOM_HEIGHT / rect.height;
  return {
    x: (clientX - rect.left) * scaleX,
    y: (clientY - rect.top) * scaleY,
  };
}

function drawBuilderObjects(ctx) {
  for (const obj of _builderObjects) {
    const cx = obj.x + obj.width / 2;
    const cy = obj.y + obj.height / 2;

    // Ground the sprite before drawing it, so builder-placed furniture is
    // planted on the floor like the lobby's own furniture.
    drawContactShadow(ctx, cx, obj.y + obj.height - 2, obj.width * 0.46, obj.height * 0.14);

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(((obj.rotation || 0) * Math.PI) / 180);

    drawFurnitureSprite(ctx, obj);

    if (obj.objectId === _selectedObjectId) {
      // Selection highlight (design doc §8.1/§13): a bright, theme-agnostic
      // dashed outline slightly outset from the object's bounds, so it reads
      // clearly against any room style's wall/floor colors. Locked objects
      // (§8.5) get a muted grey outline instead of the active cyan -- the
      // same "read as disabled" signal as the frosted lock tint below --
      // since a locked object can still be selected/inspected but not moved.
      ctx.save();
      ctx.strokeStyle = obj.isLocked ? 'rgba(180, 185, 195, 0.7)' : 'rgba(70, 190, 255, 0.95)';
      if (!obj.isLocked) {
        // Soft cyan glow on the active (unlocked) highlight only -- locked
        // objects intentionally stay flat/muted so the glow itself reads as
        // part of the "this one is editable" signal, not just decoration.
        ctx.shadowColor = 'rgba(70, 190, 255, 0.85)';
        ctx.shadowBlur = 8;
      }
      ctx.lineWidth = 2.5;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.roundRect(-obj.width / 2 - 4, -obj.height / 2 - 4, obj.width + 8, obj.height + 8, 8);
      ctx.stroke();
      ctx.restore();

      // Resize handles (§8.3): one small filled square at each corner of the
      // selection box, drawn inside this same translated+rotated context so
      // they track the object's rotation for free. Locked objects (§8.5)
      // hide them -- resizing would be rejected server-side anyway.
      if (!obj.isLocked) {
        ctx.save();
        ctx.fillStyle = '#ffffff';
        ctx.strokeStyle = 'rgba(70, 190, 255, 0.95)';
        ctx.lineWidth = 1.5;
        const hw = obj.width / 2 + 4;
        const hh = obj.height / 2 + 4;
        const half = RESIZE_HANDLE_SIZE / 2;
        for (const [sx, sy] of [
          [-1, -1],
          [1, -1],
          [-1, 1],
          [1, 1],
        ]) {
          ctx.beginPath();
          ctx.roundRect(sx * hw - half, sy * hh - half, RESIZE_HANDLE_SIZE, RESIZE_HANDLE_SIZE, 2);
          ctx.fill();
          ctx.stroke();
        }
        ctx.restore();
      }
    }

    if (obj.isLocked) {
      // Frosted tint + dashed outline reads as "locked" without hiding the
      // sprite underneath the way an opaque black overlay did.
      ctx.fillStyle = 'rgba(120,140,190,0.18)';
      ctx.beginPath();
      ctx.roundRect(-obj.width / 2, -obj.height / 2, obj.width, obj.height, 6);
      ctx.fill();

      ctx.save();
      ctx.strokeStyle = 'rgba(210,225,255,0.55)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.roundRect(-obj.width / 2 + 1, -obj.height / 2 + 1, obj.width - 2, obj.height - 2, 6);
      ctx.stroke();
      ctx.restore();
    }

    ctx.restore();
  }
}

/** Draws a builder object as a stylized furniture sprite matching its type, in a front-elevation
 * style consistent with the room's decorative furniture. Exported (design doc
 * feature_designs/build_mode_ui_redesign_feature_design.md section 9/16 Phase 1) so it can be reused
 * to render offscreen catalog-card/room-style thumbnails, not just the live room -- it already
 * only needs `{ objectType, width, height, color }` on `obj` and an arbitrary target `ctx`, with
 * no dependency on the live room's canvas size or the module-level `_builderObjects` list. */
export function drawFurnitureSprite(ctx, obj) {
  const w = obj.width;
  const h = obj.height;
  const color = resolveObjectColor(obj.color);
  switch (obj.objectType) {
    case 'table':
      drawTableSprite(ctx, w, h, color);
      break;
    case 'chair':
      drawChairSprite(ctx, w, h, color);
      break;
    case 'bar':
      drawBarSprite(ctx, w, h, color);
      break;
    case 'sofa':
      drawSofaSprite(ctx, w, h, color);
      break;
    case 'bookshelf':
      drawBookshelfSprite(ctx, w, h, color);
      break;
    case 'tv':
      drawTvSprite(ctx, w, h, color);
      break;
    case 'music_player':
      drawMusicPlayerSprite(ctx, w, h, color);
      break;
    case 'cipher_box':
      drawCipherBoxSprite(ctx, w, h, color);
      break;
    case 'digital_lock':
      drawDigitalLockSprite(ctx, w, h, color);
      break;
    case 'combination_dial':
      drawCombinationDialSprite(ctx, w, h, color);
      break;
    case 'riddle_tablet':
      drawRiddleTabletSprite(ctx, w, h, color);
      break;
    case 'clue_board':
      drawClueBoardSprite(ctx, w, h, color);
      break;
    case 'ai_character':
      // Rendered as a DOM avatar overlay (see renderAiCharacters() in
      // main.js) so AI characters share the exact same shape/rendering as
      // player avatars, instead of a hand-drawn canvas sprite.
      break;
    default:
      drawGenericSprite(ctx, w, h, obj.objectType, color);
      break;
  }
}

/** Renders a single catalog/room-object type as a small square thumbnail on an offscreen
 * canvas (design doc section 9), for use in catalog cards without duplicating any drawing code --
 * it's the same `drawFurnitureSprite` the live room uses, just aimed at a fresh canvas sized
 * `size`x`size` instead of the room canvas. Returns `null` in non-DOM environments (e.g. this
 * module's vitest suite, which runs under Node) since there's no `document` to create a canvas
 * with. */
export function renderObjectThumbnail({ objectType, color, width = 72, height = 72, size = 64 }) {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  const scale = Math.min(size / width, size / height) * 0.86;
  ctx.save();
  ctx.translate(size / 2, size / 2);
  ctx.scale(scale, scale);
  // `ai_character` deliberately draws nothing in the room (it's a DOM avatar
  // overlay), which would leave a blank card in the catalog grid. Thumbnails
  // get a stand-in bust so the card is readable.
  if (objectType === 'ai_character') drawAiCharacterBust(ctx, width, height, resolveObjectColor(color));
  else drawFurnitureSprite(ctx, { objectType, color, width, height });
  ctx.restore();
  return canvas;
}

/** Catalog-only stand-in for an AI character: a simple avatar bust that echoes
 * the SVG avatars' proportions (round head, rounded shoulders) plus a small
 * speech bubble to signal "this one talks to you". */
function drawAiCharacterBust(ctx, w, h, color) {
  const hr = Math.min(w, h) * 0.2;
  const hy = -h * 0.16;
  const skin = '#f1c27d';

  drawContactShadow(ctx, 0, h * 0.42, w * 0.3, h * 0.05, 0.3);

  // Shoulders.
  ctx.fillStyle = _matGrad(ctx, hy + hr * 0.8, h * 0.44, color, { lit: 32, base: 0, dark: -34 });
  ctx.beginPath();
  ctx.moveTo(-w * 0.32, h * 0.44);
  ctx.quadraticCurveTo(-w * 0.3, hy + hr * 1.05, -w * 0.09, hy + hr * 0.92);
  ctx.quadraticCurveTo(0, hy + hr * 1.16, w * 0.09, hy + hr * 0.92);
  ctx.quadraticCurveTo(w * 0.3, hy + hr * 1.05, w * 0.32, h * 0.44);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.28)';
  ctx.lineWidth = 1;
  ctx.stroke();

  // Neck then head.
  ctx.fillStyle = shadeColor(skin, -22);
  ctx.fillRect(-hr * 0.26, hy + hr * 0.5, hr * 0.52, hr * 0.6);
  const face = ctx.createRadialGradient(-hr * 0.3, hy - hr * 0.35, hr * 0.15, 0, hy, hr);
  face.addColorStop(0, shadeColor(skin, 30));
  face.addColorStop(1, shadeColor(skin, -16));
  ctx.fillStyle = face;
  ctx.beginPath();
  ctx.ellipse(0, hy, hr * 0.88, hr, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.24)';
  ctx.stroke();

  // Hair cap + eyes.
  ctx.fillStyle = '#4b3a2f';
  ctx.beginPath();
  ctx.ellipse(0, hy - hr * 0.28, hr * 0.9, hr * 0.66, 0, Math.PI, 0);
  ctx.fill();
  ctx.fillStyle = '#1f2937';
  for (const ex of [-hr * 0.34, hr * 0.34]) {
    ctx.beginPath();
    ctx.arc(ex, hy + hr * 0.12, Math.max(0.8, hr * 0.11), 0, Math.PI * 2);
    ctx.fill();
  }

  // Speech bubble.
  const bw = w * 0.3;
  const bh = h * 0.19;
  const bx = w * 0.16;
  const by = -h * 0.44;
  ctx.fillStyle = '#f8fafc';
  ctx.beginPath();
  ctx.roundRect(bx, by, bw, bh, bh * 0.35);
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(bx + bw * 0.18, by + bh);
  ctx.lineTo(bx + bw * 0.1, by + bh * 1.5);
  ctx.lineTo(bx + bw * 0.42, by + bh);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = '#94a3b8';
  for (let i = 0; i < 3; i++) {
    ctx.beginPath();
    ctx.arc(bx + bw * (0.28 + i * 0.22), by + bh * 0.5, Math.max(0.7, bh * 0.11), 0, Math.PI * 2);
    ctx.fill();
  }
}

/** Pure geometry for the table sprite's tabletop and legs, exported so the
 * layout can be unit tested without a canvas: legs must start flush against
 * the underside of the tabletop and run down to the sprite's bottom edge --
 * previously `legH` was a fixed fraction of `h` positioned independently
 * from the tabletop, leaving a visible gap between the legs and the
 * tabletop ("legs look off"). */
export function computeTableLayout(w, h) {
  const topH = h * 0.22;
  const topCenterY = -h / 2 + topH / 2 + 2;
  const legTopY = topCenterY + topH / 2;
  const legH = h / 2 - legTopY;
  return { topH, topCenterY, legTopY, legH };
}

/* ---------------------------------------------------------------------------
 * Puzzle prop sprites (escape_room_feature_design.md section 5.4).
 *
 * A puzzle used to be invisible until you happened to click the object it was
 * bound to. These five props give a puzzle a *readable silhouette*, so a
 * player can tell a number lock from a riddle across the room. The geometry
 * of the fiddly ones is factored into exported pure helpers -- same reasoning
 * as `computeTableLayout` -- so the layout can be unit tested under Node with
 * no canvas involved.
 * ------------------------------------------------------------------------ */

/** Pure geometry for the digital lock's LED display and its 3x4 keypad grid.
 * The button size is derived from the space actually left under the display
 * rather than being a fixed fraction of `h`, so the keypad stays inside the
 * sprite at every size preset instead of spilling out at S. */
export function computeKeypadLayout(w, h) {
  const cols = 3;
  const rows = 4;
  const padX = w * 0.14;
  const padY = h * 0.1;
  const innerW = w - padX * 2;
  const display = { x: -w / 2 + padX, y: -h / 2 + padY, w: innerW, h: h * 0.16 };
  const gridTop = display.y + display.h + h * 0.08;
  const gridH = h / 2 - padY - gridTop;
  const gap = Math.min(innerW, gridH) * 0.08;
  const size = Math.min((innerW - gap * (cols - 1)) / cols, (gridH - gap * (rows - 1)) / rows);
  const gridW = size * cols + gap * (cols - 1);
  const buttons = [];
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      buttons.push({ x: -gridW / 2 + c * (size + gap), y: gridTop + r * (size + gap), size });
    }
  }
  return { cols, rows, display, buttons };
}

/** Evenly spaced tick angles around the combination dial, starting at the top
 * (`-PI/2`) because that's the index mark you actually read a safe dial
 * against. */
export function computeDialTicks(count) {
  const step = (Math.PI * 2) / count;
  return Array.from({ length: count }, (_, i) => -Math.PI / 2 + i * step);
}

/** Pure geometry for the cipher box's stacked glyph rings: evenly divides the
 * box face into `ringCount` non-overlapping horizontal bands. */
export function computeCipherRings(w, h, ringCount) {
  const padY = h * 0.14;
  const usable = h - padY * 2;
  const gap = usable * 0.08;
  const bandH = (usable - gap * (ringCount - 1)) / ringCount;
  const inset = w * 0.12;
  return Array.from({ length: ringCount }, (_, i) => ({
    x: -w / 2 + inset,
    y: -h / 2 + padY + i * (bandH + gap),
    w: w - inset * 2,
    h: bandH,
  }));
}

function drawCipherBoxSprite(ctx, w, h, color) {
  ctx.fillStyle = _vGrad(ctx, -h / 2, h / 2, shadeColor(color, 20), shadeColor(color, -30));
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, Math.min(w, h) * 0.12);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.28)';
  ctx.lineWidth = 1.2;
  ctx.stroke();

  const rings = computeCipherRings(w, h, 3);
  rings.forEach((ring, i) => {
    ctx.fillStyle = shadeColor(color, -42);
    ctx.beginPath();
    ctx.roundRect(ring.x, ring.y, ring.w, ring.h, ring.h * 0.3);
    ctx.fill();

    // Glyph slots: the notches that make the rings read as *rotatable*
    // rather than as plain stripes.
    const slots = 4;
    const slotW = ring.w / (slots * 2);
    ctx.fillStyle = 'rgba(255, 214, 130, 0.85)';
    for (let s = 0; s < slots; s += 1) {
      const cx = ring.x + ring.w * ((s + 0.5) / slots);
      ctx.fillRect(cx - slotW / 2, ring.y + ring.h * 0.28, slotW, ring.h * 0.44);
    }
    ctx.strokeStyle = 'rgba(255,255,255,0.16)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(ring.x, ring.y + (i === 0 ? 1 : 0.5));
    ctx.lineTo(ring.x + ring.w, ring.y + (i === 0 ? 1 : 0.5));
    ctx.stroke();
  });

  ctx.fillStyle = 'rgba(255,255,255,0.2)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + 2, -h / 2 + 2, w - 4, Math.max(1, h * 0.06), 2);
  ctx.fill();
}

function drawDigitalLockSprite(ctx, w, h, color) {
  ctx.fillStyle = _vGrad(ctx, -h / 2, h / 2, shadeColor(color, 16), shadeColor(color, -34));
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, Math.min(w, h) * 0.16);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.3)';
  ctx.lineWidth = 1.2;
  ctx.stroke();

  const { display, buttons } = computeKeypadLayout(w, h);

  ctx.fillStyle = '#0e2a24';
  ctx.beginPath();
  ctx.roundRect(display.x, display.y, display.w, display.h, display.h * 0.25);
  ctx.fill();
  // Four dashes standing in for the entered code -- the visual cue that this
  // prop wants a number rather than a sentence.
  ctx.fillStyle = '#4ade80';
  const dashW = display.w / 9;
  for (let i = 0; i < 4; i += 1) {
    const cx = display.x + display.w * ((i + 0.5) / 4);
    ctx.fillRect(cx - dashW / 2, display.y + display.h * 0.55, dashW, Math.max(1, display.h * 0.16));
  }

  buttons.forEach((b, i) => {
    ctx.fillStyle = i === 10 ? shadeColor(color, -6) : shadeColor(color, -22);
    ctx.beginPath();
    ctx.roundRect(b.x, b.y, b.size, b.size, b.size * 0.28);
    ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.22)';
    ctx.fillRect(b.x + b.size * 0.18, b.y + b.size * 0.16, b.size * 0.64, Math.max(0.8, b.size * 0.12));
  });
}

function drawCombinationDialSprite(ctx, w, h, color) {
  ctx.fillStyle = _vGrad(ctx, -h / 2, h / 2, shadeColor(color, 14), shadeColor(color, -36));
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, Math.min(w, h) * 0.14);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.3)';
  ctx.lineWidth = 1.2;
  ctx.stroke();

  const radius = Math.min(w, h) * 0.36;

  ctx.fillStyle = shadeColor(color, -46);
  ctx.beginPath();
  ctx.arc(0, 0, radius * 1.18, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = _vGrad(ctx, -radius, radius, shadeColor(color, 30), shadeColor(color, -14));
  ctx.beginPath();
  ctx.arc(0, 0, radius, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = 'rgba(0,0,0,0.45)';
  ctx.lineWidth = Math.max(0.8, radius * 0.05);
  computeDialTicks(12).forEach((angle, i) => {
    const inner = radius * (i % 3 === 0 ? 0.68 : 0.8);
    ctx.beginPath();
    ctx.moveTo(Math.cos(angle) * inner, Math.sin(angle) * inner);
    ctx.lineTo(Math.cos(angle) * radius * 0.94, Math.sin(angle) * radius * 0.94);
    ctx.stroke();
  });

  // Index mark at the top, so the dial reads as "turn me to a number".
  ctx.fillStyle = '#f2cc8f';
  ctx.beginPath();
  ctx.moveTo(0, -radius * 1.18);
  ctx.lineTo(-radius * 0.13, -radius * 1.42);
  ctx.lineTo(radius * 0.13, -radius * 1.42);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = shadeColor(color, -55);
  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.2, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.beginPath();
  ctx.arc(-radius * 0.28, -radius * 0.3, radius * 0.14, 0, Math.PI * 2);
  ctx.fill();
}

function drawRiddleTabletSprite(ctx, w, h, color) {
  const baseH = h * 0.1;
  const slabH = h - baseH;
  const slabTop = -h / 2;
  const slabW = w * 0.8;

  // Stepped plinth so the stele looks planted rather than floating.
  ctx.fillStyle = shadeColor(color, -50);
  ctx.beginPath();
  ctx.roundRect(-w / 2, h / 2 - baseH, w, baseH, baseH * 0.3);
  ctx.fill();
  ctx.fillStyle = shadeColor(color, -34);
  ctx.beginPath();
  ctx.roundRect(-w * 0.42, h / 2 - baseH * 1.5, w * 0.84, baseH * 0.62, baseH * 0.25);
  ctx.fill();

  // Rounded-top slab: an upright stone, distinct from the boxy props.
  ctx.fillStyle = _matGrad(ctx, slabTop, slabTop + slabH, color, { lit: 34, base: 2, dark: -34, bandAt: 0.16 });
  ctx.beginPath();
  ctx.roundRect(-slabW / 2, slabTop, slabW, slabH, [slabW / 2, slabW / 2, 4, 4]);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.34)';
  ctx.lineWidth = 1.2;
  ctx.stroke();

  // Carved border channel, cut in shadow with a lit lower lip.
  const bi = Math.max(1.5, slabW * 0.1);
  ctx.strokeStyle = 'rgba(0,0,0,0.26)';
  ctx.lineWidth = Math.max(1, slabW * 0.045);
  ctx.beginPath();
  ctx.roundRect(-slabW / 2 + bi, slabTop + bi, slabW - bi * 2, slabH - bi * 1.6, [slabW * 0.3, slabW * 0.3, 2, 2]);
  ctx.stroke();

  // Glyph roundel near the top -- gives the prop an unmistakable "riddle" read.
  const gr = slabW * 0.17;
  const gy = slabTop + slabH * 0.19;
  ctx.fillStyle = 'rgba(0,0,0,0.3)';
  ctx.beginPath();
  ctx.arc(0, gy, gr, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = 'rgba(250,224,150,0.9)';
  ctx.beginPath();
  ctx.arc(0, gy, gr * 0.66, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(90,60,20,0.85)';
  ctx.lineWidth = Math.max(1, gr * 0.24);
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.arc(0, gy - gr * 0.14, gr * 0.28, Math.PI * 0.95, Math.PI * 0.35);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(gr * 0.05, gy - gr * 0.02);
  ctx.lineTo(gr * 0.02, gy + gr * 0.18);
  ctx.stroke();
  ctx.fillStyle = 'rgba(90,60,20,0.85)';
  ctx.beginPath();
  ctx.arc(gr * 0.02, gy + gr * 0.4, Math.max(0.7, gr * 0.12), 0, Math.PI * 2);
  ctx.fill();

  // Engraved text lines, ragged like a verse rather than a paragraph. Each
  // gets a lit lower edge so the cut looks recessed into the stone.
  const lineWidths = [0.6, 0.74, 0.66, 0.46];
  const textTop = slabTop + slabH * 0.44;
  const lineGap = slabH * 0.115;
  const lh = Math.max(1, slabH * 0.042);
  lineWidths.forEach((frac, i) => {
    const lw = slabW * frac;
    const y = textTop + i * lineGap;
    ctx.fillStyle = 'rgba(0,0,0,0.34)';
    ctx.fillRect(-lw / 2, y, lw, lh);
    ctx.fillStyle = 'rgba(255,255,255,0.2)';
    ctx.fillRect(-lw / 2, y + lh, lw, Math.max(0.5, lh * 0.4));
  });

  // Chipped corner + a hairline crack for weathered stone.
  ctx.fillStyle = 'rgba(0,0,0,0.22)';
  ctx.beginPath();
  ctx.moveTo(slabW / 2, h / 2 - baseH - slabH * 0.1);
  ctx.lineTo(slabW / 2, h / 2 - baseH);
  ctx.lineTo(slabW / 2 - slabW * 0.16, h / 2 - baseH);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.18)';
  ctx.lineWidth = Math.max(0.6, slabW * 0.02);
  ctx.beginPath();
  ctx.moveTo(-slabW * 0.34, slabTop + slabH * 0.3);
  ctx.lineTo(-slabW * 0.26, slabTop + slabH * 0.44);
  ctx.lineTo(-slabW * 0.32, slabTop + slabH * 0.6);
  ctx.stroke();

  ctx.fillStyle = 'rgba(255,255,255,0.24)';
  ctx.beginPath();
  ctx.roundRect(-slabW / 2 + 2, slabTop + 2, slabW - 4, Math.max(1, slabH * 0.05), 2);
  ctx.fill();
  _underShade(ctx, -w / 2, h / 2 - baseH, w, baseH * 0.5);
}

function drawClueBoardSprite(ctx, w, h, color) {
  ctx.fillStyle = shadeColor(color, -38);
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, Math.min(w, h) * 0.06);
  ctx.fill();

  const inset = Math.min(w, h) * 0.07;
  ctx.fillStyle = _vGrad(ctx, -h / 2, h / 2, shadeColor(color, 26), shadeColor(color, 2));
  ctx.beginPath();
  ctx.roundRect(-w / 2 + inset, -h / 2 + inset, w - inset * 2, h - inset * 2, 3);
  ctx.fill();

  // Pinned notes at slight angles -- the classic detective corkboard read.
  const notes = [
    { x: -0.28, y: -0.2, s: 0.26, tilt: -0.12, tone: '#fdf3c7' },
    { x: 0.16, y: -0.26, s: 0.22, tilt: 0.16, tone: '#ffd8c2' },
    { x: -0.06, y: 0.18, s: 0.24, tilt: -0.05, tone: '#d8ecff' },
    { x: 0.3, y: 0.14, s: 0.2, tilt: 0.1, tone: '#fdf3c7' },
  ];

  // Red string between the notes, drawn under them so the pins sit on top.
  ctx.strokeStyle = 'rgba(200, 60, 60, 0.75)';
  ctx.lineWidth = Math.max(0.8, Math.min(w, h) * 0.018);
  ctx.beginPath();
  notes.forEach((n, i) => {
    const px = n.x * w;
    const py = n.y * h;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();

  notes.forEach((n) => {
    const nw = w * n.s;
    const nh = h * n.s * 0.9;
    ctx.save();
    ctx.translate(n.x * w, n.y * h);
    ctx.rotate(n.tilt);
    ctx.fillStyle = 'rgba(0,0,0,0.18)';
    ctx.fillRect(-nw / 2 + 1, -nh / 2 + 1.5, nw, nh);
    ctx.fillStyle = n.tone;
    ctx.fillRect(-nw / 2, -nh / 2, nw, nh);
    ctx.fillStyle = 'rgba(0,0,0,0.3)';
    for (let i = 0; i < 3; i += 1) {
      ctx.fillRect(-nw * 0.32, -nh * 0.22 + i * nh * 0.22, nw * (i === 2 ? 0.4 : 0.64), Math.max(0.8, nh * 0.08));
    }
    ctx.fillStyle = '#c0392b';
    ctx.beginPath();
    ctx.arc(0, -nh / 2 + nh * 0.12, Math.max(1, nw * 0.09), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  });
}


function drawTableSprite(ctx, w, h, color) {
  const legW = w * 0.09;
  const { topH, topCenterY, legTopY, legH } = computeTableLayout(w, h);
  const topY = topCenterY - topH / 2;

  // Four legs, not two: the back pair sit inset and darker so the table has
  // depth instead of reading as a flat sign on two posts.
  const backLegW = legW * 0.8;
  ctx.fillStyle = shadeColor(color, -52);
  ctx.fillRect(-w / 2 + legW * 1.5, legTopY, backLegW, legH * 0.86);
  ctx.fillRect(w / 2 - legW * 2.3, legTopY, backLegW, legH * 0.86);

  // Front legs get their own left-lit gradient so they read as round-ish posts.
  [-w / 2 + legW * 0.6, w / 2 - legW * 1.6].forEach((lx) => {
    const g = ctx.createLinearGradient(lx, 0, lx + legW, 0);
    g.addColorStop(0, shadeColor(color, -14));
    g.addColorStop(0.35, shadeColor(color, -2));
    g.addColorStop(1, shadeColor(color, -46));
    ctx.fillStyle = g;
    ctx.fillRect(lx, legTopY, legW, legH);
    // Tapered foot + its own tiny contact darkening.
    ctx.fillStyle = shadeColor(color, -58);
    ctx.fillRect(lx, legTopY + legH - Math.max(1, legH * 0.07), legW, Math.max(1, legH * 0.07));
  });

  // Apron rail spanning the legs, just under the top.
  const apronH = Math.max(2, topH * 0.55);
  ctx.fillStyle = _vGrad(ctx, topY + topH, topY + topH + apronH, shadeColor(color, -18), shadeColor(color, -40));
  ctx.beginPath();
  ctx.roundRect(-w / 2 + legW * 0.6, topY + topH - 1, w - legW * 2.2, apronH, 2);
  ctx.fill();

  // Table top — a lit face plus a darker front edge, which gives the slab
  // visible thickness rather than the previous single flat lozenge.
  const faceH = topH * 0.62;
  ctx.fillStyle = _matGrad(ctx, topY, topY + faceH, color, { lit: 30, base: 6, dark: -8 });
  ctx.beginPath();
  ctx.roundRect(-w / 2, topY, w, faceH, [Math.min(w, h) * 0.1, Math.min(w, h) * 0.1, 1, 1]);
  ctx.fill();
  _woodGrain(ctx, -w / 2, topY, w, faceH, 3);

  ctx.fillStyle = _vGrad(ctx, topY + faceH, topY + topH, shadeColor(color, -10), shadeColor(color, -34));
  ctx.beginPath();
  ctx.roundRect(-w / 2, topY + faceH - 1, w, topH - faceH + 1, [1, 1, Math.min(w, h) * 0.06, Math.min(w, h) * 0.06]);
  ctx.fill();

  _underShade(ctx, -w / 2 + legW * 0.6, topY + topH, w - legW * 2.2, Math.max(2, h * 0.06));

  // Lit front bevel along the top edge.
  ctx.fillStyle = 'rgba(255,255,255,0.34)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + 2, topY + 1, w - 4, Math.max(1, topH * 0.12), 2);
  ctx.fill();

  // A small glass left on the table: props with a bit of "someone was here"
  // detail read far less like placeholder geometry.
  const gr = Math.min(w, h) * 0.07;
  const glassH = gr * 2.6;
  const glassY = topY - glassH;
  ctx.fillStyle = 'rgba(255,255,255,0.34)';
  ctx.beginPath();
  ctx.roundRect(-gr, glassY, gr * 2, glassH, [1, 1, gr * 0.5, gr * 0.5]);
  ctx.fill();
  ctx.fillStyle = 'rgba(129, 178, 154, 0.75)';
  ctx.beginPath();
  ctx.roundRect(-gr + 0.8, glassY + glassH * 0.35, gr * 2 - 1.6, glassH * 0.6, [0, 0, gr * 0.45, gr * 0.45]);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.fillRect(-gr + 1, glassY + glassH * 0.12, Math.max(0.8, gr * 0.3), glassH * 0.6);
}

function drawChairSprite(ctx, w, h, color) {
  const legW = w * 0.1;
  const legH = h * 0.28;
  const seatH = h * 0.22;
  const seatCenterY = h / 2 - legH - seatH / 2;
  const seatTopY = seatCenterY - seatH / 2;
  const backW = w * 0.7;
  const backH = h * 0.42;
  const backTopY = seatTopY - backH;
  const backBottomY = seatTopY;

  // Rear legs first (darker + inset) so the chair has front-to-back depth.
  ctx.fillStyle = shadeColor(color, -54);
  ctx.fillRect(-w / 2 + legW * 1.6, h / 2 - legH, legW * 0.8, legH * 0.88);
  ctx.fillRect(w / 2 - legW * 2.4, h / 2 - legH, legW * 0.8, legH * 0.88);

  // Front legs with a side-lit ramp + a stretcher rail between them.
  [-w / 2 + legW * 0.5, w / 2 - legW * 1.5].forEach((lx) => {
    const g = ctx.createLinearGradient(lx, 0, lx + legW, 0);
    g.addColorStop(0, shadeColor(color, -12));
    g.addColorStop(0.35, shadeColor(color, 2));
    g.addColorStop(1, shadeColor(color, -46));
    ctx.fillStyle = g;
    ctx.fillRect(lx, h / 2 - legH, legW, legH);
  });
  ctx.fillStyle = shadeColor(color, -34);
  ctx.fillRect(-w / 2 + legW * 0.5, h / 2 - legH * 0.42, w - legW * 2, Math.max(1, legH * 0.1));

  // Backrest: two uprights carrying a top rail and slats, instead of one slab.
  const stileW = Math.max(1.5, backW * 0.11);
  ctx.fillStyle = _matGrad(ctx, backTopY, backBottomY, color, { lit: 20, base: -6, dark: -30 });
  ctx.beginPath();
  ctx.roundRect(-backW / 2, backTopY, stileW, backH, stileW * 0.4);
  ctx.roundRect(backW / 2 - stileW, backTopY, stileW, backH, stileW * 0.4);
  ctx.fill();

  const railH = Math.max(2, backH * 0.2);
  ctx.fillStyle = _matGrad(ctx, backTopY, backTopY + railH, color, { lit: 30, base: 4, dark: -22 });
  ctx.beginPath();
  ctx.roundRect(-backW / 2, backTopY, backW, railH, railH * 0.35);
  ctx.fill();
  _underShade(ctx, -backW / 2 + stileW, backTopY + railH, backW - stileW * 2, Math.max(1.5, backH * 0.12));

  // Slats between the uprights.
  const slatW = Math.max(1.2, backW * 0.09);
  const slatTop = backTopY + railH + 1;
  const slatH = backBottomY - slatTop - 1;
  if (slatH > 1) {
    for (const frac of [-0.24, 0, 0.24]) {
      const sx = frac * backW - slatW / 2;
      ctx.fillStyle = _vGrad(ctx, slatTop, slatTop + slatH, shadeColor(color, 8), shadeColor(color, -34));
      ctx.beginPath();
      ctx.roundRect(sx, slatTop, slatW, slatH, slatW * 0.4);
      ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,0.16)';
      ctx.fillRect(sx, slatTop, Math.max(0.5, slatW * 0.3), slatH);
    }
  }

  // Upholstered seat cushion: rounded, piped, and slightly overhanging.
  ctx.fillStyle = _matGrad(ctx, seatTopY, seatCenterY + seatH / 2, color, { lit: 26, base: 2, dark: -26 });
  ctx.beginPath();
  ctx.roundRect(-w / 2, seatTopY, w, seatH, seatH * 0.34);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.22)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(-w / 2 + 2, seatTopY + 2, w - 4, seatH - 4, seatH * 0.26);
  ctx.stroke();
  ctx.fillStyle = 'rgba(255,255,255,0.26)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + 3, seatTopY + 1.5, w - 6, Math.max(1, seatH * 0.22), 2);
  ctx.fill();
  _underShade(ctx, -w / 2 + legW * 0.5, seatCenterY + seatH / 2 - 1, w - legW, Math.max(2, h * 0.05));
}

function drawSofaSprite(ctx, w, h, color) {
  const armW = w * 0.14;
  const seatH = h * 0.5;
  const seatCenterY = h / 2 - seatH;
  const backH = h * 0.34;
  const footH = Math.max(2, h * 0.07);
  const bodyBot = h / 2 - footH;

  // Small dark feet so the couch sits on the floor rather than melting into it.
  ctx.fillStyle = shadeColor(color, -62);
  ctx.fillRect(-w / 2 + armW * 0.3, bodyBot, armW * 0.5, footH);
  ctx.fillRect(w / 2 - armW * 0.8, bodyBot, armW * 0.5, footH);

  // Back cushions — two of them, so the sofa reads as upholstered furniture.
  const backTop = seatCenterY - backH;
  ctx.fillStyle = _matGrad(ctx, backTop, seatCenterY + 6, color, { lit: 34, base: 6, dark: -14 });
  ctx.beginPath();
  ctx.roundRect(-w / 2 + armW * 0.4, backTop, w - armW * 0.8, backH + 6, Math.min(10, backH * 0.4));
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.2)';
  ctx.lineWidth = 1.1;
  ctx.beginPath();
  ctx.moveTo(0, backTop + 3);
  ctx.lineTo(0, seatCenterY + 2);
  ctx.stroke();
  // Buttoned tufting dimples across the backrest.
  ctx.fillStyle = 'rgba(0,0,0,0.16)';
  for (const frac of [-0.3, -0.1, 0.1, 0.3]) {
    ctx.beginPath();
    ctx.arc(frac * w, backTop + backH * 0.45, Math.max(0.8, w * 0.012), 0, Math.PI * 2);
    ctx.fill();
  }

  // Rolled arms: a body plus a lit cap ellipse reads round, a plain rounded
  // rect reads like a slab of card.
  [-w / 2, w / 2 - armW].forEach((ax, i) => {
    ctx.fillStyle = _matGrad(ctx, seatCenterY - 4, bodyBot, color, { lit: 12, base: -14, dark: -34 });
    ctx.beginPath();
    ctx.roundRect(ax, seatCenterY - 4, armW, bodyBot - seatCenterY + 4, [armW * 0.5, armW * 0.5, 4, 4]);
    ctx.fill();
    const g = ctx.createRadialGradient(
      ax + armW * (i === 0 ? 0.35 : 0.65), seatCenterY - 1, armW * 0.1,
      ax + armW * 0.5, seatCenterY + armW * 0.2, armW * 0.9,
    );
    g.addColorStop(0, shadeColor(color, 42));
    g.addColorStop(1, shadeColor(color, -18));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.ellipse(ax + armW * 0.5, seatCenterY - 1, armW * 0.5, armW * 0.42, 0, 0, Math.PI * 2);
    ctx.fill();
  });

  // Seat cushions — split into two with a visible seam and piping.
  const seatBot = bodyBot;
  ctx.fillStyle = _matGrad(ctx, seatCenterY, seatBot, color, { lit: 20, base: -4, dark: -30 });
  ctx.beginPath();
  ctx.roundRect(-w / 2 + armW * 0.85, seatCenterY, w - armW * 1.7, seatBot - seatCenterY, 6);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.22)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(-w / 2 + armW * 0.85 + 1.5, seatCenterY + 1.5, w - armW * 1.7 - 3, (seatBot - seatCenterY) - 3, 5);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(0,0,0,0.24)';
  ctx.lineWidth = 1.3;
  ctx.beginPath();
  ctx.moveTo(0, seatCenterY + 3);
  ctx.lineTo(0, seatBot - 3);
  ctx.stroke();

  _underShade(ctx, -w / 2 + armW * 0.85, seatCenterY, w - armW * 1.7, Math.max(2, seatH * 0.18));
  ctx.fillStyle = 'rgba(255,255,255,0.14)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + armW * 1.05, seatCenterY + 2, w - armW * 2.1, Math.max(1, seatH * 0.16), 3);
  ctx.fill();

  // A throw pillow tucked into the left corner.
  const pw = Math.min(w, h) * 0.2;
  ctx.save();
  ctx.translate(-w / 2 + armW * 1.25, seatCenterY - pw * 0.15);
  ctx.rotate(-0.22);
  ctx.fillStyle = shadeColor(color, 58);
  ctx.beginPath();
  ctx.roundRect(-pw / 2, -pw / 2, pw, pw, pw * 0.22);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.2)';
  ctx.lineWidth = 0.9;
  ctx.stroke();
  ctx.restore();
}

function drawBarSprite(ctx, w, h, color) {
  const counterCenterY = h / 2 - h * 0.3;
  const shelfBot = -h / 2 + h * 0.3;

  // Back-bar unit: a recessed, darker niche the bottles sit inside.
  ctx.fillStyle = shadeColor(color, -52);
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h * 0.3, [3, 3, 0, 0]);
  ctx.fill();
  ctx.fillStyle = _vGrad(ctx, -h / 2 + 2, shelfBot, shadeColor(color, -66), shadeColor(color, -40));
  ctx.fillRect(-w / 2 + 2, -h / 2 + 2, w - 4, h * 0.3 - 3);

  // Bottles with necks, shoulders and a specular stripe: the previous flat
  // rectangles were the single most obviously placeholder part of this prop.
  const bottleColors = ['#e07a5f', '#81b29a', '#f2cc8f', '#3d405b', '#c084fc'];
  const bw = w * 0.075;
  for (let i = 0; i < 5; i += 1) {
    const bx = -w / 2 + (i + 0.75) * (w / 5.7);
    const bh = h * 0.24 * (i % 2 === 0 ? 1 : 0.84);
    const by = shelfBot - 2 - bh;
    const tone = bottleColors[i % bottleColors.length];
    ctx.fillStyle = tone;
    ctx.beginPath();
    ctx.roundRect(bx, by + bh * 0.34, bw, bh * 0.66, [bw * 0.3, bw * 0.3, 1, 1]);
    ctx.fill();
    ctx.fillRect(bx + bw * 0.34, by, bw * 0.32, bh * 0.4);
    ctx.fillStyle = 'rgba(255,255,255,0.45)';
    ctx.fillRect(bx + bw * 0.16, by + bh * 0.42, Math.max(0.6, bw * 0.18), bh * 0.44);
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.fillRect(bx + bw * 0.34, by, bw * 0.32, Math.max(0.8, bh * 0.07));
  }
  // Glass shelf edge catching the light.
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.fillRect(-w / 2 + 2, shelfBot - 2, w - 4, Math.max(1, h * 0.014));

  // Counter body with vertical panelling.
  const bodyTop = -h * 0.2;
  ctx.fillStyle = _matGrad(ctx, bodyTop, h / 2, color, { lit: 4, base: -18, dark: -44 });
  ctx.fillRect(-w / 2, bodyTop, w, h / 2 - bodyTop);
  ctx.strokeStyle = 'rgba(0,0,0,0.22)';
  ctx.lineWidth = 1;
  for (const frac of [-0.25, 0, 0.25]) {
    ctx.beginPath();
    ctx.moveTo(frac * w, bodyTop + h * 0.06);
    ctx.lineTo(frac * w, h / 2 - h * 0.12);
    ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(255,255,255,0.1)';
  for (const frac of [-0.25, 0, 0.25]) {
    ctx.beginPath();
    ctx.moveTo(frac * w + 1, bodyTop + h * 0.06);
    ctx.lineTo(frac * w + 1, h / 2 - h * 0.12);
    ctx.stroke();
  }

  // Overhanging counter top with a lit nosing and shadow beneath.
  const topH = Math.max(4, h * 0.075);
  ctx.fillStyle = _matGrad(ctx, counterCenterY - topH, counterCenterY + topH * 0.4, color, { lit: 40, base: 8, dark: -12 });
  ctx.beginPath();
  ctx.roundRect(-w / 2 - 3, counterCenterY - topH, w + 6, topH * 1.4, 3);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.42)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 - 3, counterCenterY - topH, w + 6, Math.max(1, topH * 0.34), 2);
  ctx.fill();
  _underShade(ctx, -w / 2, counterCenterY + topH * 0.4, w, Math.max(2, h * 0.05));

  // Brass foot rail + plinth.
  ctx.strokeStyle = 'rgba(242, 204, 143, 0.75)';
  ctx.lineWidth = Math.max(1, h * 0.018);
  ctx.beginPath();
  ctx.moveTo(-w / 2 + w * 0.06, h / 2 - h * 0.12);
  ctx.lineTo(w / 2 - w * 0.06, h / 2 - h * 0.12);
  ctx.stroke();
  ctx.fillStyle = shadeColor(color, -58);
  ctx.fillRect(-w / 2, h / 2 - 4, w, 4);
}

function drawBookshelfSprite(ctx, w, h, color) {
  // Outer case, gradient-shaded so the wood catches the room light.
  ctx.fillStyle = _vGrad(ctx, -h / 2, h / 2, shadeColor(color, -6), shadeColor(color, -40));
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, 4);
  ctx.fill();

  const innerX = -w / 2 + w * 0.08;
  const innerW = w * 0.84;

  // Recessed interior, so the shelves read as depth rather than stripes.
  ctx.fillStyle = shadeColor(color, -58);
  ctx.beginPath();
  ctx.roundRect(innerX, -h / 2 + h * 0.03, innerW, h * 0.94, 2);
  ctx.fill();

  const shelfCount = 3;
  const shelfGap = h / shelfCount;
  const bookColors = ['#e07a5f', '#81b29a', '#f2cc8f', '#3d405b', '#c084fc', '#67e8f9'];
  let colorIdx = 0;

  for (let s = 0; s < shelfCount; s++) {
    const shelfY = -h / 2 + s * shelfGap;
    const rowH = shelfGap - 4;

    const bookCount = 4 + (s % 2);
    const eachW = (innerW - 4) / bookCount;
    for (let b = 0; b < bookCount; b++) {
      const bh = rowH * (0.7 + (0.25 * ((b + s) % 3)) / 2);
      const bx = innerX + 2 + b * eachW;
      const by = shelfY + 2 + (rowH - bh);
      const bw = eachW - 2;
      const spine = bookColors[colorIdx % bookColors.length];
      colorIdx++;

      ctx.fillStyle = _vGrad(ctx, by, by + bh, shadeColor(spine, 20), shadeColor(spine, -25));
      ctx.fillRect(bx, by, bw, bh);
      // Lit edge + gold band: the detail that makes a block read as a book.
      ctx.fillStyle = 'rgba(255,255,255,0.22)';
      ctx.fillRect(bx, by, Math.max(1, bw * 0.2), bh);
      ctx.fillStyle = 'rgba(255,222,150,0.5)';
      ctx.fillRect(bx + bw * 0.15, by + bh * 0.3, bw * 0.7, Math.max(1, bh * 0.05));
    }

    // Shelf plank with a lit top edge.
    const plankY = shelfY + shelfGap - 3;
    ctx.fillStyle = shadeColor(color, -2);
    ctx.fillRect(-w / 2, plankY, w, 3);
    ctx.fillStyle = 'rgba(255,255,255,0.24)';
    ctx.fillRect(-w / 2, plankY, w, 1);
  }

  // Rim light along the top and left of the case.
  ctx.fillStyle = 'rgba(255,255,255,0.18)';
  ctx.fillRect(-w / 2, -h / 2, w, 1.5);
  ctx.fillRect(-w / 2, -h / 2, 1.5, h);
}

function drawTvSprite(ctx, w, h, color) {
  const screenH = h * 0.62;
  const bezelPad = Math.min(w, h) * 0.06;

  ctx.fillStyle = shadeColor(color, -30);
  ctx.fillRect(-w * 0.12, h / 2 - h * 0.14, w * 0.24, h * 0.14);
  ctx.beginPath();
  ctx.roundRect(-w * 0.3, h / 2 - 5, w * 0.6, 5, 2);
  ctx.fill();

  ctx.fillStyle = '#1a1a1a';
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, screenH, 4);
  ctx.fill();

  const grad = ctx.createLinearGradient(0, -h / 2, 0, -h / 2 + screenH);
  grad.addColorStop(0, shadeColor(color, 40));
  grad.addColorStop(1, shadeColor(color, -10));
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.roundRect(-w / 2 + bezelPad, -h / 2 + bezelPad, w - bezelPad * 2, screenH - bezelPad * 2, 2);
  ctx.fill();

  ctx.fillStyle = 'rgba(255,255,255,0.75)';
  ctx.beginPath();
  ctx.moveTo(-w * 0.08, -h / 2 + screenH / 2 - h * 0.08);
  ctx.lineTo(-w * 0.08, -h / 2 + screenH / 2 + h * 0.08);
  ctx.lineTo(w * 0.1, -h / 2 + screenH / 2);
  ctx.closePath();
  ctx.fill();

  // Diagonal glass glare, clipped to the panel so it reads as reflection.
  ctx.save();
  ctx.beginPath();
  ctx.rect(-w / 2 + bezelPad, -h / 2 + bezelPad, w - bezelPad * 2, screenH - bezelPad * 2);
  ctx.clip();
  ctx.fillStyle = 'rgba(255,255,255,0.10)';
  ctx.beginPath();
  ctx.moveTo(-w / 2, -h / 2 + screenH);
  ctx.lineTo(-w / 2 + w * 0.4, -h / 2);
  ctx.lineTo(-w / 2 + w * 0.68, -h / 2);
  ctx.lineTo(-w / 2 + w * 0.06, -h / 2 + screenH);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawMusicPlayerSprite(ctx, w, h, color) {
  // Chassis with a lit top face and a shadowed front, so the deck reads as a
  // box you could stand behind.
  ctx.fillStyle = _matGrad(ctx, -h * 0.34, h * 0.34, color, { lit: 22, base: -12, dark: -42 });
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h * 0.34, w, h * 0.68, Math.min(w, h) * 0.08);
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.3)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = 'rgba(255,255,255,0.22)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + 2, -h * 0.34 + 1.5, w - 4, Math.max(1, h * 0.05), 2);
  ctx.fill();

  // ONE platter on the left plus a mixer panel on the right. Two identical
  // dark circles side by side read unmistakably as a pair of goggles.
  const r = Math.min(w * 0.34, h * 0.26);
  const px = -w * 0.26;

  ctx.fillStyle = 'rgba(0,0,0,0.3)';
  ctx.beginPath();
  ctx.arc(px, r * 0.12, r * 1.06, 0, Math.PI * 2);
  ctx.fill();

  const vinyl = ctx.createRadialGradient(px - r * 0.3, -r * 0.3, r * 0.1, px, 0, r);
  vinyl.addColorStop(0, '#3b4453');
  vinyl.addColorStop(0.55, '#1f2937');
  vinyl.addColorStop(1, '#0d1219');
  ctx.fillStyle = vinyl;
  ctx.beginPath();
  ctx.arc(px, 0, r, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = 'rgba(255,255,255,0.12)';
  ctx.lineWidth = 0.8;
  for (const f of [0.5, 0.68, 0.86]) {
    ctx.beginPath();
    ctx.arc(px, 0, r * f, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(255,255,255,0.3)';
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.arc(px, 0, r * 0.93, Math.PI * 1.05, Math.PI * 1.55);
  ctx.stroke();

  // Label + spindle.
  ctx.fillStyle = shadeColor(color, 40);
  ctx.beginPath();
  ctx.arc(px, 0, r * 0.34, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#e8edf5';
  ctx.beginPath();
  ctx.arc(px, 0, Math.max(0.7, r * 0.07), 0, Math.PI * 2);
  ctx.fill();

  // Tonearm sweeping in from the upper right of the platter.
  ctx.strokeStyle = '#cbd5e1';
  ctx.lineWidth = Math.max(1, r * 0.11);
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(px + r * 1.05, -r * 0.95);
  ctx.lineTo(px + r * 0.15, r * 0.4);
  ctx.stroke();
  ctx.fillStyle = '#94a3b8';
  ctx.beginPath();
  ctx.arc(px + r * 1.05, -r * 0.95, Math.max(1, r * 0.16), 0, Math.PI * 2);
  ctx.fill();

  // Mixer panel: channel faders, a crossfader and two knobs.
  const mx = w * 0.22;
  const mw = w * 0.4;
  const mh = h * 0.46;
  ctx.fillStyle = shadeColor(color, -46);
  ctx.beginPath();
  ctx.roundRect(mx - mw / 2, -mh / 2, mw, mh, 2);
  ctx.fill();

  ctx.fillStyle = 'rgba(0,0,0,0.45)';
  for (const f of [-0.26, 0, 0.26]) {
    ctx.fillRect(mx + f * mw - Math.max(0.5, mw * 0.02), -mh * 0.38, Math.max(1, mw * 0.04), mh * 0.44);
  }
  ctx.fillStyle = '#e2e8f0';
  [-0.26, 0, 0.26].forEach((f, i) => {
    const t = [-0.06, -0.2, 0.02][i];
    ctx.fillRect(mx + f * mw - mw * 0.08, mh * t, mw * 0.16, Math.max(1, mh * 0.06));
  });
  // Crossfader along the bottom.
  ctx.fillStyle = 'rgba(0,0,0,0.45)';
  ctx.fillRect(mx - mw * 0.36, mh * 0.24, mw * 0.72, Math.max(1, mh * 0.06));
  ctx.fillStyle = '#e2e8f0';
  ctx.fillRect(mx - mw * 0.06, mh * 0.19, mw * 0.12, Math.max(1.5, mh * 0.16));

  // Level LEDs.
  ctx.fillStyle = '#4ade80';
  ctx.fillRect(mx - mw * 0.44, -mh * 0.36, Math.max(1, mw * 0.05), Math.max(1, mh * 0.3));
  ctx.fillStyle = '#f87171';
  ctx.fillRect(mx - mw * 0.44, -mh * 0.42, Math.max(1, mw * 0.05), Math.max(1, mh * 0.07));

  // Feet.
  ctx.fillStyle = shadeColor(color, -58);
  ctx.fillRect(-w / 2 + 2, h * 0.3, w * 0.1, h * 0.1);
  ctx.fillRect(w / 2 - w * 0.1 - 2, h * 0.3, w * 0.1, h * 0.1);
}

function drawGenericSprite(ctx, w, h, objectType, color) {
  const r = Math.min(w, h) * 0.16;

  // Base body with a specular band and a darkened, rounded lower edge.
  ctx.fillStyle = _matGrad(ctx, -h / 2, h / 2, color, { lit: 32, base: -2, dark: -34 });
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, r);
  ctx.fill();

  // Inner bevel: a bright top-left rim and a dark bottom-right rim, which is
  // what makes a shape read as a solid extruded object under a ceiling light.
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, r);
  ctx.clip();
  ctx.lineWidth = Math.max(1.5, Math.min(w, h) * 0.06);
  ctx.strokeStyle = 'rgba(255,255,255,0.34)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + 1, -h / 2 + 1, w - 2, h - 2, r);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(0,0,0,0.26)';
  ctx.beginPath();
  ctx.moveTo(-w / 2 + 1, h / 2 - 1);
  ctx.lineTo(w / 2 - 1, h / 2 - 1);
  ctx.lineTo(w / 2 - 1, -h / 2 + 1);
  ctx.stroke();

  // Soft diagonal sheen across the upper-left face.
  const sheen = ctx.createLinearGradient(-w / 2, -h / 2, w * 0.2, h * 0.3);
  sheen.addColorStop(0, 'rgba(255,255,255,0.24)');
  sheen.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = sheen;
  ctx.beginPath();
  ctx.moveTo(-w / 2, -h / 2);
  ctx.lineTo(w * 0.16, -h / 2);
  ctx.lineTo(-w / 2, h * 0.16);
  ctx.closePath();
  ctx.fill();
  ctx.restore();

  // Outer contour keeps the prop legible against similarly-toned room styles.
  ctx.strokeStyle = 'rgba(0,0,0,0.28)';
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, r);
  ctx.stroke();

  const fs = Math.min(w, h, 28);
  ctx.font = `${fs}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  ctx.fillText(objectTypeIcon(objectType), 0, fs * 0.06);
  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  ctx.fillText(objectTypeIcon(objectType), 0, 0);
}
