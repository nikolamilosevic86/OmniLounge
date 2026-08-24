/**
 * Combat UI — keyboard bindings, nearest-target lookup, attack animation dispatch.
 *
 * Air punch: animation always plays immediately on keypress.
 * Damage:    server decides — client never suppresses the socket emit.
 * Range:     server validates; if out of range the combat:hit event is not sent.
 */
import { ATTACK_TYPES } from './combat.js';
import { ATTACK_DURATIONS, getBlockAngles } from './attack-anim.js';

let _socket         = null;
let _getMyId        = null;
let _getMyPos       = null;
let _getPlayers     = null;
let _onAttackStart  = null;   // callback(playerId, type, startMs, duration)
let _lastAttack     = { punch: 0, kick: 0 };
let _blocking       = false;
let _enabled        = false;

export function initCombat({ socket, getMyId, getMyPos, getPlayers, onAttackStart }) {
  _socket        = socket;
  _getMyId       = getMyId;
  _getMyPos      = getMyPos;
  _getPlayers    = getPlayers;
  _onAttackStart = onAttackStart;
  _enabled       = true;

  window.addEventListener('keydown', _onKeyDown);
  window.addEventListener('keyup',   _onKeyUp);
}

export function destroyCombat() {
  _enabled = false;
  window.removeEventListener('keydown', _onKeyDown);
  window.removeEventListener('keyup',   _onKeyUp);
}

export function isBlocking() { return _blocking; }

// ── helpers ────────────────────────────────────────────────────────────────────

function _isTyping() {
  const tag = document.activeElement?.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA';
}

function _nearestTarget() {
  const myId  = _getMyId();
  const myPos = _getMyPos();
  if (!myPos) return null;

  let nearest = null, nearestDist = Infinity;
  for (const [id, player] of _getPlayers()) {
    if (id === myId) continue;
    const dx = player.position.x - myPos.x;
    const dy = player.position.y - myPos.y;
    const d  = Math.sqrt(dx * dx + dy * dy);
    if (d < nearestDist) { nearestDist = d; nearest = player; }
  }
  return nearest;
}

function _tryAttack(type) {
  if (!_enabled || _isTyping()) return;

  const now = Date.now();
  const cfg = ATTACK_TYPES[type];
  if (!cfg) return;

  // Client-side cooldown prevents animation spam — matches server cooldown
  if (now - (_lastAttack[type] || 0) < cfg.cooldownMs) return;
  _lastAttack[type] = now;

  // ── Always start the local animation (air punch is allowed) ──
  const duration = ATTACK_DURATIONS[type] ?? cfg.cooldownMs;
  const target = _nearestTarget();
  const myPos = _getMyPos();
  // facingRight: punch/kick toward the target; if no target, default true
  const facingRight = !target || !myPos || target.position.x >= myPos.x;
  _onAttackStart?.(_getMyId(), type, now, duration, facingRight);

  // ── Always emit to server; server validates range and applies damage ──
  if (target) {
    _socket.emit('combat:attack', { type, targetId: target.id });
  }
}

function _onKeyDown(e) {
  if (!_enabled || _isTyping()) return;

  if (e.code === 'Space') {
    e.preventDefault();
    _tryAttack('punch');
  } else if (
    (e.code === 'ControlLeft' || e.code === 'ControlRight' ||
     e.code === 'MetaLeft'    || e.code === 'MetaRight') &&
    !e.shiftKey && !e.altKey
  ) {
    e.preventDefault();
    _tryAttack('kick');
  } else if (e.code === 'KeyB') {
    e.preventDefault();
    if (!_blocking) {
      _blocking = true;
      _socket.emit('combat:block', { blocking: true });
    }
  }
}

function _onKeyUp(e) {
  if (!_enabled) return;
  if (e.code === 'KeyB' && _blocking) {
    _blocking = false;
    _socket?.emit('combat:block', { blocking: false });
  }
}

