/**
 * Client-side copy of src/combat.js
 * (Vite cannot serve files outside its root; src/ is for tests only.)
 */
export const ATTACK_TYPES = {
  punch: { damage: 12, staminaCost: 8,  range: 80, cooldownMs: 600,  label: 'Punch' },
  kick:  { damage: 20, staminaCost: 15, range: 90, cooldownMs: 1000, label: 'Kick'  },
};
export const MAX_STAMINA    = 100;
export const BLOCK_REDUCTION = 0.65;
export const REGEN_PER_MS   = 18 / 1000; // 18 hp/sec — sustained aggression still KOs, brief exchanges don't

export function calculateDamage(type, blocked = false) {
  const cfg = ATTACK_TYPES[type];
  if (!cfg) return 0;
  return blocked ? Math.round(cfg.damage * (1 - BLOCK_REDUCTION)) : cfg.damage;
}
export function canAttack(stamina, lastAttackMs, nowMs, type) {
  const cfg = ATTACK_TYPES[type];
  if (!cfg) return false;
  if (stamina < cfg.staminaCost) return false;
  if (nowMs - lastAttackMs < cfg.cooldownMs) return false;
  return true;
}
export function isInRange(pos1, pos2, type) {
  const cfg = ATTACK_TYPES[type];
  if (!cfg) return false;
  const dx = pos1.x - pos2.x;
  const dy = pos1.y - pos2.y;
  return Math.sqrt(dx * dx + dy * dy) <= cfg.range;
}
export function applyHit(stamina, damage) { return Math.max(0, stamina - damage); }
export function regenStamina(stamina, deltaMs) {
  return Math.min(MAX_STAMINA, stamina + REGEN_PER_MS * deltaMs);
}
export function isStunned(stamina) { return stamina <= 0; }
