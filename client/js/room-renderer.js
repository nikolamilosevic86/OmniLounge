const ROOM_WIDTH = 800;
const ROOM_HEIGHT = 600;
const WALL_HEIGHT = ROOM_HEIGHT * 0.42;

let _animFrame = null;
let _canvas = null;

export function drawRoom(canvas) {
  _canvas = canvas;
  if (_animFrame) cancelAnimationFrame(_animFrame);
  _animLoop();
}

function _animLoop() {
  const ctx = _canvas.getContext('2d');
  ctx.clearRect(0, 0, ROOM_WIDTH, ROOM_HEIGHT);

  drawBackdrop(ctx);
  drawWall(ctx);
  drawFloor(ctx);
  drawFurniture(ctx);
  drawAmbientLight(ctx);
  drawDiscoBall(ctx, ROOM_WIDTH / 2, WALL_HEIGHT * 0.22);

  _animFrame = requestAnimationFrame(_animLoop);
}

function drawBackdrop(ctx) {
  const grad = ctx.createLinearGradient(0, 0, 0, ROOM_HEIGHT);
  grad.addColorStop(0, '#2a2438');
  grad.addColorStop(1, '#1c1828');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, ROOM_WIDTH, ROOM_HEIGHT);
}

function drawWall(ctx) {
  const grad = ctx.createLinearGradient(0, 0, 0, WALL_HEIGHT);
  grad.addColorStop(0, '#4a3f5c');
  grad.addColorStop(1, '#6e6082');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, ROOM_WIDTH, WALL_HEIGHT);

  // subtle vertical panel lines
  ctx.fillStyle = 'rgba(255,255,255,0.03)';
  for (let x = 0; x < ROOM_WIDTH; x += 80) {
    ctx.fillRect(x, 0, 1, WALL_HEIGHT);
  }

  drawWindow(ctx, ROOM_WIDTH * 0.08, ROOM_HEIGHT * 0.06, ROOM_WIDTH * 0.28, ROOM_HEIGHT * 0.22);
  drawWindow(ctx, ROOM_WIDTH * 0.64, ROOM_HEIGHT * 0.06, ROOM_WIDTH * 0.28, ROOM_HEIGHT * 0.22);

  drawWallArt(ctx, ROOM_WIDTH * 0.42, ROOM_HEIGHT * 0.08, 70, 50);

  ctx.fillStyle = '#584e6a';
  ctx.fillRect(0, WALL_HEIGHT - 6, ROOM_WIDTH, 8);
  ctx.fillStyle = '#483e5a';
  ctx.fillRect(0, WALL_HEIGHT - 2, ROOM_WIDTH, 4);
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

  for (let row = 0; row < 12; row++) {
    for (let col = 0; col < 18; col++) {
      const x = col * tileW + (row % 2 ? tileW / 2 : 0);
      const y = floorY + row * tileH;
      const shade = (row + col) % 2 === 0 ? '#c9a87c' : '#b8956a';
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
  drawSofa(ctx, 60, ROOM_HEIGHT * 0.58, '#5b4a8a');       // muted indigo
  drawSofa(ctx, ROOM_WIDTH - 210, ROOM_HEIGHT * 0.58, '#7a4060');  // muted rose
  drawPlant(ctx, 20, WALL_HEIGHT - 10);
  drawPlant(ctx, ROOM_WIDTH - 55, WALL_HEIGHT - 10);
  drawCoffeeTable(ctx, ROOM_WIDTH / 2 - 50, ROOM_HEIGHT * 0.62);
  drawNeonSign(ctx, ROOM_WIDTH / 2, WALL_HEIGHT - 30);
  drawDJDeck(ctx, ROOM_WIDTH * 0.15, ROOM_HEIGHT * 0.72);
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
  ctx.fillText('✦ HOBBOVERSE ✦', x, y);
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
  const lampX = ROOM_WIDTH / 2;
  const lampY = WALL_HEIGHT;
  const grad = ctx.createRadialGradient(lampX, lampY, 10, lampX, lampY + 100, 280);
  grad.addColorStop(0, 'rgba(255, 200, 150, 0.12)');
  grad.addColorStop(1, 'rgba(255, 200, 150, 0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, WALL_HEIGHT, ROOM_WIDTH, ROOM_HEIGHT - WALL_HEIGHT);
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
