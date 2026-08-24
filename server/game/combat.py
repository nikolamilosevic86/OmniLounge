import math

ATTACK_TYPES = {
    "punch": {"damage": 12, "stamina_cost": 8,  "range": 80, "cooldown_ms": 600},
    "kick":  {"damage": 20, "stamina_cost": 15, "range": 90, "cooldown_ms": 1000},
}

MAX_STAMINA     = 100.0
BLOCK_REDUCTION = 0.65
REGEN_PER_MS    = 18.0 / 1000.0  # 18 hp/sec — sustained aggression still KOs, brief exchanges don't
STUN_DURATION_MS    = 300_000.0  # 5 minutes


def calculate_damage(attack_type: str, blocked: bool = False) -> int:
    cfg = ATTACK_TYPES.get(attack_type)
    if not cfg:
        return 0
    return round(cfg["damage"] * (1 - BLOCK_REDUCTION)) if blocked else cfg["damage"]


def can_attack(stamina: float, last_attack_ms: float, now_ms: float,
               attack_type: str, stunned_until_ms: float = 0.0) -> bool:
    if now_ms < stunned_until_ms:
        return False
    cfg = ATTACK_TYPES.get(attack_type)
    if not cfg:
        return False
    if stamina < cfg["stamina_cost"]:
        return False
    if now_ms - last_attack_ms < cfg["cooldown_ms"]:
        return False
    return True


def is_in_range(pos1: dict, pos2: dict, attack_type: str) -> bool:
    cfg = ATTACK_TYPES.get(attack_type)
    if not cfg:
        return False
    dx = pos1["x"] - pos2["x"]
    dy = pos1["y"] - pos2["y"]
    return math.sqrt(dx * dx + dy * dy) <= cfg["range"]


def apply_hit(stamina: float, damage: int) -> float:
    return max(0.0, stamina - damage)


def regen_stamina(stamina: float, delta_ms: float) -> float:
    return min(MAX_STAMINA, stamina + REGEN_PER_MS * delta_ms)
