/**
 * Attack animation math — arcade-style (80s/90s fighter).
 *
 * ─── SVG rotate() sign convention (mathematically verified — see
 * tests/attack-anim.test.js "geometric anchor" tests) ───────────────────────
 * Pivot is at the TOP of each limb (shoulder / hip); the limb hangs DOWN
 * at rest. Rotating by θ maps the hanging point (0, L) to (−L·sinθ, L·cosθ).
 *
 *   NEGATIVE angle → limb swings RIGHT
 *   POSITIVE angle → limb swings LEFT
 *
 * Do NOT flip these signs without re-running the geometric anchor tests.
 *
 * Punch: 3-phase (wind-up → fast snap → retract)
 * Kick:  2-phase (fast raise → slower lower)
 * Block: linear ramp to cross-guard (both arms swing INWARD toward center)
 */

export const ATTACK_DURATIONS = { punch: 420, kick: 640 };

export function computeAttackPhase(startMs, nowMs, durationMs) {
  if (durationMs <= 0) return 1;
  return Math.min(1, Math.max(0, (nowMs - startMs) / durationMs));
}

const WINDUP_END  = 0.18;
const PEAK_AT     = 0.46;
const WINDUP_FRAC = 0.14;

// punchCurve: negative during wind-up (arm pulled back), rises through 0,
// reaches +1 at the peak (full extension), then decays back to 0.
function punchCurve(phase) {
  if (phase <= 0 || phase >= 1) return 0;
  if (phase < WINDUP_END)
    return -(phase / WINDUP_END) * WINDUP_FRAC;
  if (phase < PEAK_AT) {
    const t = (phase - WINDUP_END) / (PEAK_AT - WINDUP_END);
    return -WINDUP_FRAC + t * (1 + WINDUP_FRAC);
  }
  return 1 - (phase - PEAK_AT) / (1 - PEAK_AT);
}

const KICK_PEAK_AT = 0.42;

function kickCurve(phase) {
  if (phase <= 0 || phase >= 1) return 0;
  if (phase < KICK_PEAK_AT) return phase / KICK_PEAK_AT;
  return 1 - (phase - KICK_PEAK_AT) / (1 - KICK_PEAK_AT);
}

const PUNCH_PEAK    = 88;
const PUNCH_BALANCE = 22;
const KICK_PEAK     = 90;
const KICK_SUPPORT  = 14;
const KICK_ARM_SPL  = 28;
const GUARD_ANGLE   = 80;

export function getPunchAngles(phase, facingRight = true) {
  const p = punchCurve(phase);
  // Strike arm must swing TOWARD the opponent: negative angle = right,
  // positive angle = left. Balance arm counter-swings AWAY from opponent.
  return facingRight
    ? { rightArmAngle: parseFloat((-p * PUNCH_PEAK).toFixed(2)),
        leftArmAngle:  parseFloat((p * PUNCH_BALANCE).toFixed(2)),
        leftLegAngle: 0, rightLegAngle: 0 }
    : { leftArmAngle:  parseFloat((p * PUNCH_PEAK).toFixed(2)),
        rightArmAngle: parseFloat((-p * PUNCH_BALANCE).toFixed(2)),
        leftLegAngle: 0, rightLegAngle: 0 };
}

export function getKickAngles(phase, facingRight = true) {
  const k = kickCurve(phase);
  // Kick leg swings TOWARD the opponent; support leg shifts slightly away.
  // Arms splay outward (opposite senses) for balance, independent of facing.
  return facingRight
    ? { rightLegAngle: parseFloat((-k * KICK_PEAK).toFixed(2)),
        leftLegAngle:  parseFloat((k * KICK_SUPPORT).toFixed(2)),
        leftArmAngle:  parseFloat((k * KICK_ARM_SPL).toFixed(2)),
        rightArmAngle: parseFloat((-k * KICK_ARM_SPL).toFixed(2)) }
    : { leftLegAngle:  parseFloat((k * KICK_PEAK).toFixed(2)),
        rightLegAngle: parseFloat((-k * KICK_SUPPORT).toFixed(2)),
        leftArmAngle:  parseFloat((k * KICK_ARM_SPL).toFixed(2)),
        rightArmAngle: parseFloat((-k * KICK_ARM_SPL).toFixed(2)) };
}

export function getBlockAngles(phase) {
  const p = Math.min(1, Math.max(0, phase));
  const a = parseFloat((p * GUARD_ANGLE).toFixed(2));
  // Cross guard: LEFT arm swings RIGHT (negative) toward center; RIGHT arm
  // swings LEFT (positive) toward center. This CLOSES the guard inward.
  return { leftArmAngle: parseFloat((-a).toFixed(2)), rightArmAngle: a };
}
