import { io } from 'socket.io-client';
import { AVATAR_OPTIONS, renderAvatarSVG } from './avatar-renderer.js';
import { drawRoom, canvasToRoomCoords } from './room-renderer.js';
import { advanceWalkPhase } from './animation.js';
import { getObjectAtPoint } from './room-objects.js';
import { showRadialMenu, dismissRadialMenu, hasActiveMenu } from './radial-menu.js';
import { initCombat, destroyCombat, isBlocking } from './combat-ui.js';
import { ATTACK_DURATIONS, computeAttackPhase, getPunchAngles, getKickAngles, getBlockAngles } from './attack-anim.js';

const BUBBLE_DURATION = 6000;

const state = {
  avatar: {
    username: '',
    skinColor: AVATAR_OPTIONS.skinColors[0],
    hair: AVATAR_OPTIONS.hair[0],
    beard: 'none',
    glasses: 'none',
    clothes: AVATAR_OPTIONS.clothes[0],
    accessory: 'none',
  },
  playerId: null,
  players: new Map(),
  activeBubbles: new Map(),
  walkPhases: new Map(),   // playerId → { phase, lastX, lastY }
  talkingUntil: new Map(), // playerId → timestamp ms
  blinkDelay: new Map(),   // playerId → css delay string
  actionStates: new Map(), // playerId → actionState string|null
  playerStamina: new Map(), // playerId → number 0-100
  playerBlocking: new Map(), // playerId → bool
  playerStunned: new Map(),  // playerId → stunnedUntil ms
  hitFlash: new Map(),       // playerId → expiry ms
  attackAnim: new Map(),     // playerId → { type, startMs, duration, facingRight }
  blockAnim: new Map(),      // playerId → { phase, entering, startMs }
  wasStunned: new Map(),     // playerId → bool (previous frame)
  wakingUpUntil: new Map(),  // playerId → timestamp ms
  chatMode: 'public',
  socket: null,
  keys: { ArrowUp: false, ArrowDown: false, ArrowLeft: false, ArrowRight: false },
  gameLoopId: null,
};

const creatorScreen = document.getElementById('creator-screen');
const gameScreen = document.getElementById('game-screen');
const avatarPreview = document.getElementById('avatar-preview');
const usernameInput = document.getElementById('username-input');
const enterRoomBtn = document.getElementById('enter-room-btn');
const roomCanvas = document.getElementById('room-canvas');
const playersLayer = document.getElementById('players-layer');
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const recipientSelect = document.getElementById('recipient-select');
const recipientDropdown = document.getElementById('recipient-dropdown');
const onlineCount = document.getElementById('online-count');

function initCreator() {
  buildColorSwatches();
  buildOptionButtons('hair-options', AVATAR_OPTIONS.hair, 'hair');
  buildOptionButtons('beard-options', AVATAR_OPTIONS.beards, 'beard');
  buildOptionButtons('glasses-options', AVATAR_OPTIONS.glasses, 'glasses');
  buildOptionButtons('clothes-options', AVATAR_OPTIONS.clothes, 'clothes');
  buildOptionButtons('accessory-options', AVATAR_OPTIONS.accessories, 'accessory');

  usernameInput.addEventListener('input', () => {
    state.avatar.username = usernameInput.value.trim();
    enterRoomBtn.disabled = state.avatar.username.length === 0;
  });

  enterRoomBtn.addEventListener('click', enterRoom);
  updateAvatarPreview();
}

function buildColorSwatches() {
  const container = document.getElementById('skin-colors');
  AVATAR_OPTIONS.skinColors.forEach(color => {
    const swatch = document.createElement('button');
    swatch.className = 'color-swatch' + (color === state.avatar.skinColor ? ' selected' : '');
    swatch.style.backgroundColor = color;
    swatch.title = color;
    swatch.addEventListener('click', () => {
      state.avatar.skinColor = color;
      container.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('selected'));
      swatch.classList.add('selected');
      updateAvatarPreview();
    });
    container.appendChild(swatch);
  });
}

function buildOptionButtons(containerId, options, field) {
  const container = document.getElementById(containerId);
  options.forEach(option => {
    const btn = document.createElement('button');
    btn.className = 'option-btn' + (option === state.avatar[field] ? ' selected' : '');
    btn.textContent = option;
    btn.addEventListener('click', () => {
      state.avatar[field] = option;
      container.querySelectorAll('.option-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      updateAvatarPreview();
    });
    container.appendChild(btn);
  });
}

function updateAvatarPreview() {
  avatarPreview.innerHTML = renderAvatarSVG(state.avatar, 'large');
}

function enterRoom() {
  if (!state.avatar.username) return;
  creatorScreen.classList.remove('active');
  gameScreen.classList.add('active');
  initGame();
  connectSocket();
}

function initGame() {
  drawRoom(roomCanvas);

  roomCanvas.addEventListener('click', (e) => {
    const coords = canvasToRoomCoords(roomCanvas, e.clientX, e.clientY);

    // If clicking on an interactive object, show the radial menu
    const obj = getObjectAtPoint(coords.x, coords.y);
    if (obj) {
      showRadialMenu(playersLayer, coords.x, coords.y, obj, (action) => {
        state.socket?.emit('player:action', {
          actionState: action.actionState,
          target: action.target,
          teleport: action.actionState === 'on-table',
        });
      });
      return;  // don't move player
    }

    // Otherwise move the player
    dismissRadialMenu();
    state.socket?.emit('player:move', coords);
    clearKeyboardDirection();
    spawnClickMarker(coords.x, coords.y);
  });

  // Escape dismisses the menu
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') dismissRadialMenu();
  });

  document.getElementById('mode-public').addEventListener('click', () => setChatMode('public'));
  document.getElementById('mode-private').addEventListener('click', () => setChatMode('private'));
  chatForm.addEventListener('submit', (e) => { e.preventDefault(); sendMessage(); });

  // Show talking animation while typing in chat box
  chatInput.addEventListener('input', () => {
    if (state.playerId && chatInput.value.trim()) {
      state.talkingUntil.set(state.playerId, Date.now() + 1500);
    }
  });

  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);

  state.gameLoopId = setInterval(() => {
    renderPlayers();
    pruneExpiredBubbles();
  }, 33);
}

function onKeyDown(e) {
  if (!state.keys.hasOwnProperty(e.key)) return;
  if (document.activeElement === chatInput) return;
  e.preventDefault();
  state.keys[e.key] = true;
  emitDirection();
}

function onKeyUp(e) {
  if (!state.keys.hasOwnProperty(e.key)) return;
  state.keys[e.key] = false;
  emitDirection();
}

function getDirectionFromKeys() {
  let x = 0;
  let y = 0;
  if (state.keys.ArrowLeft) x -= 1;
  if (state.keys.ArrowRight) x += 1;
  if (state.keys.ArrowUp) y -= 1;
  if (state.keys.ArrowDown) y += 1;
  return { x, y };
}

function emitDirection() {
  const dir = getDirectionFromKeys();
  state.socket?.emit('player:direction', dir);
}

function clearKeyboardDirection() {
  Object.keys(state.keys).forEach(k => { state.keys[k] = false; });
  state.socket?.emit('player:direction', { x: 0, y: 0 });
}

function setChatMode(mode) {
  state.chatMode = mode;
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
  recipientSelect.classList.toggle('hidden', mode === 'public');
}

function connectSocket() {
  state.socket = io(window.location.origin, { transports: ['websocket', 'polling'] });

  state.socket.on('connect', () => {
    state.playerId = state.socket.id;
    state.socket.emit('player:join', { avatar: state.avatar });

    // Init combat bindings once socket is ready
    initCombat({
      socket:        state.socket,
      getMyId:       () => state.playerId,
      getMyPos:      () => state.players.get(state.playerId)?.position ?? null,
      getPlayers:    () => state.players,
      onAttackStart: (playerId, type, startMs, duration, facingRight) => {
        state.attackAnim.set(playerId, { type, startMs, duration, facingRight: facingRight ?? true });
      },
    });
  });

  state.socket.on('player:joined', (data) => {
    state.playerId = data.id;
    state.players.set(data.id, { id: data.id, avatar: data.avatar, position: data.position });
    state.playerStamina.set(data.id, data.stamina ?? 100);
    renderPlayers();
  });

  state.socket.on('combat:hit', (evt) => {
    const now = Date.now();
    state.playerStamina.set(evt.targetId,   evt.targetStamina);
    state.playerStamina.set(evt.attackerId, evt.attackerStamina ?? state.playerStamina.get(evt.attackerId) ?? 100);
    state.hitFlash.set(evt.targetId, now + 460);
    // Compute facingRight for remote/AI attackers from their current positions
    const attackerPos = state.players.get(evt.attackerId)?.position;
    const targetPos   = state.players.get(evt.targetId)?.position;
    const facingRight = !attackerPos || !targetPos || targetPos.x >= attackerPos.x;
    const duration = ATTACK_DURATIONS[evt.type] ?? 480;
    state.attackAnim.set(evt.attackerId, { type: evt.type, startMs: now, duration, facingRight });
    if (evt.stunnedUntil > 0) state.playerStunned.set(evt.targetId, evt.stunnedUntil);
    renderPlayers();
  });

  state.socket.on('room:state', (data) => {
    data.players.forEach(p => {
      const existing = state.players.get(p.id);
      if (existing) {
        existing.position    = p.position;
        existing.avatar      = p.avatar;
        existing.actionState = p.actionState ?? null;
      } else {
        state.players.set(p.id, p);
      }
      state.actionStates.set(p.id,   p.actionState  ?? null);
      state.playerStamina.set(p.id,  p.stamina       ?? 100);
      state.playerBlocking.set(p.id, p.blocking      ?? false);
      if (p.stunnedUntil > 0) state.playerStunned.set(p.id, p.stunnedUntil);
    });
    renderPlayers();
    updateOnlineCount();
    updateRecipientList();
  });

  state.socket.on('player:entered', (data) => {
    state.players.set(data.id, data);
    renderPlayers();
    updateOnlineCount();
    updateRecipientList();
    addSystemMessage(`${data.avatar.username} entered the lounge`);
  });

  state.socket.on('player:left', (data) => {
    const player = state.players.get(data.id);
    if (player) addSystemMessage(`${player.avatar.username} left the lounge`);
    state.players.delete(data.id);
    state.activeBubbles.delete(data.id);
    state.walkPhases.delete(data.id);
    state.talkingUntil.delete(data.id);
    state.blinkDelay.delete(data.id);
    state.actionStates.delete(data.id);
    state.playerStamina.delete(data.id);
    state.playerBlocking.delete(data.id);
    state.playerStunned.delete(data.id);
    state.hitFlash.delete(data.id);
    state.attackAnim.delete(data.id);
    state.wasStunned.delete(data.id);
    state.wakingUpUntil.delete(data.id);
    renderPlayers();
    updateOnlineCount();
    updateRecipientList();
  });

  state.socket.on('chat:message', (msg) => {
    appendChatMessage(msg);
    showBubble(msg.senderId, msg.text, msg.type);
  });

  state.socket.on('chat:history', (messages) => {
    messages.forEach(msg => {
      appendChatMessage(msg);
      showBubble(msg.senderId, msg.text, msg.type, msg.timestamp);
    });
  });

  state.socket.on('chat:bubbles', (bubbles) => {
    bubbles.forEach(b => showBubble(b.senderId, b.text, b.type, b.timestamp));
  });

  state.socket.on('error', (err) => console.error('Server error:', err.message));

  // Block animation for remote players
  state.socket.on('combat:block_update', (evt) => {
    if (evt.blocking) {
      state.blockAnim.set(evt.playerId, { phase: 0, entering: true, startMs: Date.now() });
    } else {
      const current = state.blockAnim.get(evt.playerId);
      if (current) {
        state.blockAnim.set(evt.playerId, { phase: current.phase, entering: false, startMs: Date.now() });
      }
    }
  });
}

function showBubble(senderId, text, type, timestamp) {
  const now = Date.now();
  state.activeBubbles.set(senderId, {
    text,
    type,
    addedAt: now,
    expiresAt: (timestamp || now) + BUBBLE_DURATION,
  });
  // Mark the sender as talking for 3 seconds
  state.talkingUntil.set(senderId, now + 3000);
  renderPlayers();
}

function spawnClickMarker(x, y) {
  const el = document.createElement('div');
  el.className = 'click-marker';
  el.style.left = `${x}px`;
  el.style.top  = `${y}px`;
  el.innerHTML = `<svg viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="18" cy="18" r="14" stroke="#ff6b9d" stroke-width="2.5" stroke-dasharray="5 3"/>
    <circle cx="18" cy="18" r="5" fill="#ff6b9d" opacity="0.85"/>
    <circle cx="18" cy="18" r="2" fill="white"/>
  </svg>`;
  playersLayer.appendChild(el);
  el.addEventListener('animationend', () => el.remove());
}

function pruneExpiredBubbles() {
  const now = Date.now();
  let changed = false;
  for (const [id, bubble] of state.activeBubbles) {
    if (bubble.expiresAt <= now) {
      state.activeBubbles.delete(id);
      changed = true;
    }
  }
  if (changed) renderPlayers();
}

function renderPlayers() {
  const sorted = [...state.players.values()].sort((a, b) => a.position.y - b.position.y);
  const now = Date.now();

  // ── remove elements for players who have left ────────────────────────────
  for (const el of [...playersLayer.querySelectorAll('.room-player')]) {
    if (!state.players.has(el.dataset.pid)) el.remove();
  }

  // ── update / create each player element in sorted z-order ────────────────
  for (let i = 0; i < sorted.length; i++) {
    const player = sorted[i];

    // walk phase
    let wt = state.walkPhases.get(player.id);
    if (!wt) {
      wt = { phase: 0, lastX: player.position.x, lastY: player.position.y };
      state.walkPhases.set(player.id, wt);
    }
    const moved = player.position.x !== wt.lastX || player.position.y !== wt.lastY;
    wt.phase = advanceWalkPhase(wt.phase, moved);
    wt.lastX = player.position.x;
    wt.lastY = player.position.y;

    const talking = (state.talkingUntil.get(player.id) || 0) > now;
    const actionState = state.actionStates.get(player.id) ?? player.actionState ?? null;

    // ── block animation phase ────────────────────────────────────────────────
    const isLocalPlayer = player.id === state.playerId;
    const isCurrentlyBlocking = isLocalPlayer ? isBlocking() : (state.playerBlocking.get(player.id) ?? false);
    // Advance block phase (200ms enter, 150ms exit)
    let ba = state.blockAnim.get(player.id);
    if (isCurrentlyBlocking && (!ba || !ba.entering)) {
      ba = { phase: ba?.phase ?? 0, entering: true, startMs: now };
      state.blockAnim.set(player.id, ba);
    } else if (!isCurrentlyBlocking && ba?.entering) {
      ba = { phase: ba.phase, entering: false, startMs: now };
      state.blockAnim.set(player.id, ba);
    }
    let blockPhase = 0;
    if (ba) {
      const elapsed = now - ba.startMs;
      if (ba.entering) {
        blockPhase = Math.min(1, ba.phase + elapsed / 200);
      } else {
        blockPhase = Math.max(0, ba.phase - elapsed / 150);
        if (blockPhase === 0) state.blockAnim.delete(player.id);
      }
      if (ba.entering) ba.phase = blockPhase; // update for next frame
    }

    if (!state.blinkDelay.has(player.id)) {
      state.blinkDelay.set(player.id, `${(Math.random() * 4).toFixed(2)}s`);
    }
    const blinkDelay = state.blinkDelay.get(player.id);

    // ── find or create the wrapper div ──────────────────────────────────────
    let el = playersLayer.querySelector(`[data-pid="${CSS.escape(player.id)}"]`);
    const isNew = !el;
    if (isNew) {
      el = document.createElement('div');
      el.dataset.pid = player.id;
    }

    el.className = 'room-player' + (player.id === state.playerId ? ' is-self' : '');
    el.style.left = `${player.position.x}px`;
    el.style.top  = `${player.position.y}px`;
    el.style.zIndex = i + 1;

    // ── bubble: only touch the DOM when content changes ─────────────────────
    const bubble = state.activeBubbles.get(player.id);
    let bubbleEl = el.querySelector('.speech-bubble');

    if (bubble) {
      const lockIcon = bubble.type === 'private' ? '<span class="bubble-lock">🔒</span>' : '';
      const desiredText = lockIcon + escapeHtml(bubble.text);

      if (!bubbleEl) {
        // First appearance — create and animate in
        bubbleEl = document.createElement('div');
        bubbleEl.className = 'speech-bubble' + (bubble.type === 'private' ? ' private' : '');
        bubbleEl.innerHTML = desiredText;
        el.insertBefore(bubbleEl, el.firstChild);
      } else if (bubbleEl.innerHTML !== desiredText) {
        // Text updated (shouldn't happen often) — update in place, no animation restart
        bubbleEl.innerHTML = desiredText;
      }
    } else if (bubbleEl) {
      // Bubble expired — fade out then remove
      bubbleEl.classList.add('fading');
      bubbleEl.addEventListener('animationend', () => bubbleEl.remove(), { once: true });
    }

    // ── avatar SVG ───────────────────────────────────────────────────────────
    const blocking    = state.playerBlocking.get(player.id) ?? false;
    const stunnedUntil = state.playerStunned.get(player.id) ?? 0;
    const stunned     = stunnedUntil > now;
    const isHit       = (state.hitFlash.get(player.id) ?? 0) > now;

    // Compute smooth attack angles from timing data
    const attackInfo = state.attackAnim.get(player.id);
    let attackAngles = null;
    if (attackInfo && !stunned) {
      const phase = computeAttackPhase(attackInfo.startMs, now, attackInfo.duration);
      if (phase < 1) {
        const facingRight = attackInfo.facingRight ?? true;
        attackAngles = attackInfo.type === 'kick'
          ? getKickAngles(phase, facingRight)
          : getPunchAngles(phase, facingRight);
      }
    }

    // If not attacking, use block angles if blocking
    if (!attackAngles && blockPhase > 0) {
      const ba_ = getBlockAngles(blockPhase);
      attackAngles = { ...ba_, leftLegAngle: 0, rightLegAngle: 0 };
    }

    // KO / wake-up class management
    const prevStunned = state.wasStunned.get(player.id) ?? false;
    state.wasStunned.set(player.id, stunned);
    if (prevStunned && !stunned) {
      state.wakingUpUntil.set(player.id, now + 800);
    }
    const isWakingUp = (state.wakingUpUntil.get(player.id) ?? 0) > now;
    if (stunned)    el.classList.add('is-ko');
    else            el.classList.remove('is-ko');
    if (isWakingUp) el.classList.add('is-waking-up');
    else            el.classList.remove('is-waking-up');

    const newSvg = renderAvatarSVG(
      player.avatar, 'normal',
      (stunned || isWakingUp) ? 0 : wt.phase,
      talking, actionState, false, attackAngles
    );
    let svgEl = el.querySelector('.avatar-svg');
    const tmp = document.createElement('div');
    tmp.innerHTML = newSvg;
    const newSvgEl = tmp.firstElementChild;
    if (!stunned && !isWakingUp) {
      newSvgEl.style.animationDelay = blinkDelay;
      newSvgEl.querySelectorAll('.eye-l, .eye-r').forEach(eye => {
        eye.style.animationDelay = blinkDelay;
        const cx = eye.querySelector('ellipse')?.getAttribute('cx') || '50%';
        const cy = eye.querySelector('ellipse')?.getAttribute('cy') || '50%';
        eye.style.transformOrigin = `${cx}px ${cy}px`;
      });
    }
    if (talking)              newSvgEl.classList.add('is-talking');
    if (isHit && !stunned)    newSvgEl.classList.add('avatar-hit');
    if (stunned)              newSvgEl.classList.add('avatar-ko-pose');

    if (svgEl) {
      el.replaceChild(newSvgEl, svgEl);
    } else {
      el.appendChild(newSvgEl);
    }

    // ── KO ♥ ZZZ indicator ─────────────────────────────────────────────────
    let zzzEl = el.querySelector('.ko-zzz');
    if (stunned && !zzzEl) {
      zzzEl = document.createElement('span');
      zzzEl.className = 'ko-zzz';
      zzzEl.textContent = '💤';
      el.appendChild(zzzEl);
    } else if (!stunned && zzzEl) {
      zzzEl.remove();
    }

    // ── stamina bar ──────────────────────────────────────────────────────────
    const stamina = state.playerStamina.get(player.id) ?? 100;
    let barWrap = el.querySelector('.stamina-bar');
    if (!barWrap) {
      barWrap = document.createElement('div');
      barWrap.className = 'stamina-bar';
      barWrap.innerHTML = '<div class="stamina-fill"></div>';
      el.appendChild(barWrap);
    }
    const fill = barWrap.querySelector('.stamina-fill');
    fill.style.width = `${Math.max(0, stamina)}%`;
    fill.style.background = stamina > 60 ? '#22c55e' : stamina > 25 ? '#fbbf24' : '#ef4444';
    barWrap.title = `${Math.round(stamina)} HP`;

    // ── name tag ────────────────────────────────────────────────────────────
    let nameEl = el.querySelector('.player-name');
    if (!nameEl) {
      nameEl = document.createElement('span');
      nameEl.className = 'player-name';
      el.appendChild(nameEl);
    }
    nameEl.textContent = stunned ? `KO  ${player.avatar.username}` : player.avatar.username;

    // ── self indicator ──────────────────────────────────────────────────────
    if (player.id === state.playerId && !el.querySelector('.self-indicator')) {
      const si = document.createElement('span');
      si.className = 'self-indicator';
      el.appendChild(si);
    }

    if (isNew) playersLayer.appendChild(el);
  }
}

function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  const payload = { text, type: state.chatMode };
  if (state.chatMode === 'private') {
    const recipientId = recipientDropdown.value;
    if (!recipientId) return;
    payload.recipientId = recipientId;
  }

  state.socket.emit('chat:send', payload);
  chatInput.value = '';
}

function appendChatMessage(msg) {
  const el = document.createElement('div');
  el.className = 'chat-message' + (msg.type === 'private' ? ' private' : '');
  const time = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const tag = msg.type === 'private' ? '<span class="msg-tag">whisper</span>' : '';
  el.innerHTML = `<span class="msg-time">${time}</span>` +
    `<span class="msg-sender">${escapeHtml(msg.senderName)}</span>` +
    `<span class="msg-text">${escapeHtml(msg.text)}</span>${tag}`;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addSystemMessage(text) {
  const el = document.createElement('div');
  el.className = 'chat-message system';
  el.textContent = text;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function updateOnlineCount() {
  onlineCount.textContent = `${state.players.size} online`;
}

function updateRecipientList() {
  recipientDropdown.innerHTML = '<option value="">Select player...</option>';
  for (const [id, player] of state.players) {
    if (id === state.playerId) continue;
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = player.avatar.username;
    recipientDropdown.appendChild(opt);
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

initCreator();
