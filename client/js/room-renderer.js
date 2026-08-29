import { resolveObjectColor, objectTypeIcon } from './builder-objects.js';
import { resolveRoomStyle, DEFAULT_ROOM_STYLE } from './room-styles.js';

const ROOM_WIDTH = 800;
const ROOM_HEIGHT = 600;
const WALL_HEIGHT = ROOM_HEIGHT * 0.42;

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

/** Vertical linear gradient between two shades, in the CURRENT transform's
 * local space — so sprite helpers can call it after ctx.translate/rotate. */
function _vGrad(ctx, y0, y1, top, bottom) {
  const grad = ctx.createLinearGradient(0, y0, 0, y1);
  grad.addColorStop(0, top);
  grad.addColorStop(1, bottom);
  return grad;
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
      // clearly against any room style's wall/floor colors.
      ctx.save();
      ctx.strokeStyle = 'rgba(70, 190, 255, 0.95)';
      ctx.lineWidth = 2.5;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.roundRect(-obj.width / 2 - 4, -obj.height / 2 - 4, obj.width + 8, obj.height + 8, 8);
      ctx.stroke();
      ctx.restore();
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
  drawFurnitureSprite(ctx, { objectType, color, width, height });
  ctx.restore();
  return canvas;
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

function drawTableSprite(ctx, w, h, color) {
  const legW = w * 0.09;
  const { topH, topCenterY, legTopY, legH } = computeTableLayout(w, h);

  ctx.fillStyle = shadeColor(color, -35);
  ctx.fillRect(-w / 2 + legW * 0.6, legTopY, legW, legH);
  ctx.fillRect(w / 2 - legW * 1.6, legTopY, legW, legH);

  ctx.fillStyle = _vGrad(ctx, topCenterY - topH / 2, topCenterY + topH / 2, shadeColor(color, 22), shadeColor(color, -18));
  ctx.beginPath();
  ctx.roundRect(-w / 2, topCenterY - topH / 2, w, topH, Math.min(w, h) * 0.12);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.28)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + 2, topCenterY - topH / 2 + 1.5, w - 4, Math.max(1, topH * 0.16), 2);
  ctx.fill();

  ctx.fillStyle = 'rgba(255,255,255,0.25)';
  ctx.beginPath();
  ctx.arc(0, topCenterY - topH / 2 - 2, Math.min(w, h) * 0.08, 0, Math.PI * 2);
  ctx.fill();
}

function drawChairSprite(ctx, w, h, color) {
  const legW = w * 0.1;
  const legH = h * 0.28;
  const seatH = h * 0.22;
  const seatCenterY = h / 2 - legH - seatH / 2;
  const backW = w * 0.7;
  const backH = h * 0.42;

  ctx.fillStyle = shadeColor(color, -35);
  ctx.fillRect(-w / 2 + legW * 0.5, h / 2 - legH, legW, legH);
  ctx.fillRect(w / 2 - legW * 1.5, h / 2 - legH, legW, legH);

  ctx.fillStyle = _vGrad(ctx, seatCenterY - seatH / 2 - backH, seatCenterY - seatH / 2, shadeColor(color, 14), shadeColor(color, -22));
  ctx.beginPath();
  ctx.roundRect(-backW / 2, seatCenterY - seatH / 2 - backH, backW, backH, 4);
  ctx.fill();

  ctx.fillStyle = _vGrad(ctx, seatCenterY - seatH / 2, seatCenterY + seatH / 2, shadeColor(color, 16), shadeColor(color, -18));
  ctx.beginPath();
  ctx.roundRect(-w / 2, seatCenterY - seatH / 2, w, seatH, 4);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.12)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + 3, seatCenterY - seatH / 2 + 2, w - 6, seatH * 0.4, 2);
  ctx.fill();
}

function drawSofaSprite(ctx, w, h, color) {
  const armW = w * 0.14;
  const seatH = h * 0.5;
  const seatCenterY = h / 2 - seatH;
  const backH = h * 0.34;

  ctx.fillStyle = shadeColor(color, -20);
  ctx.beginPath();
  ctx.roundRect(-w / 2, seatCenterY - 4, armW, seatH + 4, 6);
  ctx.fill();
  ctx.beginPath();
  ctx.roundRect(w / 2 - armW, seatCenterY - 4, armW, seatH + 4, 6);
  ctx.fill();

  ctx.fillStyle = _vGrad(ctx, seatCenterY - backH, seatCenterY + 6, shadeColor(color, 28), shadeColor(color, -6));
  ctx.beginPath();
  ctx.roundRect(-w / 2 + armW * 0.4, seatCenterY - backH, w - armW * 0.8, backH + 6, 6);
  ctx.fill();

  ctx.fillStyle = _vGrad(ctx, seatCenterY, seatCenterY + seatH, shadeColor(color, 12), shadeColor(color, -22));
  ctx.beginPath();
  ctx.roundRect(-w / 2 + armW * 0.3, seatCenterY, w - armW * 0.6, seatH, 6);
  ctx.fill();

  ctx.strokeStyle = 'rgba(0,0,0,0.15)';
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(0, seatCenterY + 3);
  ctx.lineTo(0, seatCenterY + seatH - 3);
  ctx.stroke();

  ctx.fillStyle = 'rgba(255,255,255,0.1)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + armW * 0.6, seatCenterY + 3, w - armW * 1.2, seatH * 0.35, 4);
  ctx.fill();
}

function drawBarSprite(ctx, w, h, color) {
  const counterCenterY = h / 2 - h * 0.3;

  ctx.fillStyle = shadeColor(color, -40);
  ctx.fillRect(-w / 2, -h / 2, w, h * 0.3);

  const bottleColors = ['#e07a5f', '#81b29a', '#f2cc8f', '#3d405b'];
  for (let i = 0; i < 4; i++) {
    ctx.fillStyle = bottleColors[i % bottleColors.length];
    const bx = -w / 2 + (i + 0.7) * (w / 4.6);
    ctx.fillRect(bx, -h / 2 + 2, w * 0.06, h * 0.24);
  }

  ctx.fillStyle = shadeColor(color, -15);
  ctx.fillRect(-w / 2, -h * 0.2, w, h * 0.42);

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(-w / 2 - 3, counterCenterY - 6, w + 6, 10, 3);
  ctx.fill();
  ctx.fillStyle = shadeColor(color, 20);
  ctx.beginPath();
  ctx.roundRect(-w / 2 - 3, counterCenterY - 6, w + 6, 4, 2);
  ctx.fill();

  ctx.fillStyle = shadeColor(color, -45);
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
  ctx.fillStyle = shadeColor(color, -20);
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h * 0.3, w, h * 0.6, 3);
  ctx.fill();

  const r = Math.min(w, h) * 0.22;
  ctx.fillStyle = '#1f2937';
  ctx.beginPath();
  ctx.arc(-w * 0.22, 0, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(w * 0.22, 0, r, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(-w * 0.22, 0, r * 0.35, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(w * 0.22, 0, r * 0.35, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = shadeColor(color, -40);
  ctx.fillRect(-w / 2 + 2, h * 0.28, w * 0.08, h * 0.14);
  ctx.fillRect(w / 2 - w * 0.08 - 2, h * 0.28, w * 0.08, h * 0.14);
}

function drawGenericSprite(ctx, w, h, objectType, color) {
  ctx.fillStyle = _vGrad(ctx, -h / 2, h / 2, shadeColor(color, 26), shadeColor(color, -26));
  ctx.strokeStyle = 'rgba(255,255,255,0.3)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, 8);
  ctx.fill();
  ctx.stroke();

  // Glossy top-half highlight, like a moulded plastic prop.
  ctx.fillStyle = 'rgba(255,255,255,0.12)';
  ctx.beginPath();
  ctx.roundRect(-w / 2 + 3, -h / 2 + 3, w - 6, h * 0.4, 6);
  ctx.fill();

  ctx.fillStyle = 'rgba(255,255,255,0.95)';
  ctx.font = `${Math.min(w, h, 28)}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(objectTypeIcon(objectType), 0, 0);
}
