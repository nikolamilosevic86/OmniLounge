import math
import random
from typing import Any, Optional

from server.game.combat import (
    ATTACK_TYPES, MAX_STAMINA, STUN_DURATION_MS,
    calculate_damage, is_in_range,
)
from server.game.movement import clamp_position, ROOM_BOUNDS

BOT_ID = "ai-bot"
BOT_AVATAR = {
    "username": "RoboFighter",
    "skinColor": "#8D5524",
    "hair": "mohawk",
    "beard": "none",
    "glasses": "sunglasses",
    "clothes": "jacket",
    "accessory": "headphones",
}

_TRASH_TALK = [
    "Come at me! 👊",
    "Is that all you've got?",
    "My circuits are OVERCLOCKED 🔥",
    "Heh, nice try human.",
    "Error 404: Weakness not found.",
    "I don't feel pain. But you will.",
    "ENGAGING COMBAT PROTOCOL 🤖",
    "Fascinating. Let me recalibrate.",
    "You fight like a corrupted RAM stick.",
    "404 DAMAGE NOT FOUND",
]

_WANDER_INTERVAL_S = 3.5
_CHAT_INTERVAL_S   = 9.0
_APPROACH_RANGE    = 180.0
_ATTACK_RANGE      = 85.0
_BLOCK_PROB        = 0.22
_KICK_PROB         = 0.35


class AIBot:
    def __init__(self) -> None:
        self.wander_target: Optional[dict] = None
        self.last_wander_s  = 0.0
        self.last_chat_s    = 0.0
        self.last_attack_ms: dict[str, float] = {"punch": 0.0, "kick": 0.0}
        self.blocking       = False
        self.pending_chat: Optional[str] = None
        self.stunned_until_ms = 0.0

    # ── helpers ───────────────────────────────────────────────────────────────

    def _pick_wander(self) -> dict:
        return clamp_position({
            "x": random.uniform(80, ROOM_BOUNDS["maxX"] - 80),
            "y": random.uniform(340, ROOM_BOUNDS["maxY"] - 40),
        })

    def _bot_and_nearest(self, players: list) -> tuple[Optional[dict], Optional[dict], float]:
        bot = next((p for p in players if p["id"] == BOT_ID), None)
        if not bot:
            return None, None, 0.0
        others = [p for p in players if p["id"] != BOT_ID]
        if not others:
            return bot, None, 0.0
        bx, by = bot["position"]["x"], bot["position"]["y"]
        nearest = min(others, key=lambda p: math.hypot(
            p["position"]["x"] - bx, p["position"]["y"] - by))
        dist = math.hypot(nearest["position"]["x"] - bx, nearest["position"]["y"] - by)
        return bot, nearest, dist

    # ── tick ─────────────────────────────────────────────────────────────────

    def tick(self, now_s: float, players: list) -> Optional[dict]:
        """
        Run one AI frame.  Returns an attack event dict if the bot attacks,
        otherwise None.  Shape: {type, targetId, damage, blocked}.
        May also set self.pending_chat.
        """
        bot, nearest, dist = self._bot_and_nearest(players)
        if not bot:
            return None

        now_ms = now_s * 1000

        # Skip if stunned
        if now_ms < self.stunned_until_ms:
            bot["targetPosition"] = None
            return None

        # ── chat ─────────────────────────────────────────────────────────────
        if nearest and dist < 250 and now_s - self.last_chat_s > _CHAT_INTERVAL_S:
            self.pending_chat = random.choice(_TRASH_TALK)
            self.last_chat_s = now_s

        # ── state / movement ─────────────────────────────────────────────────
        if nearest and dist < _APPROACH_RANGE:
            if dist > _ATTACK_RANGE * 0.88:
                bot["targetPosition"] = nearest["position"]
            else:
                bot["targetPosition"] = None
                bot["direction"] = {"x": 0, "y": 0}

            self.blocking = random.random() < _BLOCK_PROB

            # Attack decision
            target_stunned = now_ms < nearest.get("stunnedUntil", 0)
            if not target_stunned and is_in_range(bot["position"], nearest["position"], "punch"):
                atype = "kick" if random.random() < _KICK_PROB else "punch"
                cfg   = ATTACK_TYPES[atype]
                last  = self.last_attack_ms[atype]
                if (now_ms - last >= cfg["cooldown_ms"]
                        and bot.get("stamina", MAX_STAMINA) >= cfg["stamina_cost"]):
                    self.last_attack_ms[atype] = now_ms
                    bot["stamina"] = max(0.0, bot.get("stamina", MAX_STAMINA) - cfg["stamina_cost"])
                    target_blocked = nearest.get("blocking", False)
                    dmg = calculate_damage(atype, target_blocked)
                    return {
                        "type": atype,
                        "targetId": nearest["id"],
                        "damage": dmg,
                        "blocked": target_blocked,
                    }
        else:
            self.blocking = False
            if now_s - self.last_wander_s > _WANDER_INTERVAL_S or not self.wander_target:
                self.wander_target = self._pick_wander()
                self.last_wander_s = now_s
            bot["targetPosition"] = self.wander_target

        bot["blocking"] = self.blocking
        return None

    def on_hit(self, now_ms: float) -> None:
        """Called by the server when the bot takes lethal-stun-level damage."""
        self.stunned_until_ms = now_ms + STUN_DURATION_MS
