"""Tests for `server/game/ai_bot.py` — the practice-fight AI bot's per-tick
decision logic (movement, chat trash-talk, attack selection, stun handling).
This module previously had zero test coverage even though its `tick()`
method is the sole driver of bot behavior seen by every player who spars
with it. Randomness in `tick()` is controlled deterministically here via
monkeypatching `server.game.ai_bot.random`.
"""

import pytest

from server.game.ai_bot import AIBot, BOT_ID, BOT_AVATAR
from server.game.combat import ATTACK_TYPES, MAX_STAMINA


def _bot_player(**overrides):
    player = {
        "id": BOT_ID,
        "position": {"x": 400, "y": 400},
        "stamina": MAX_STAMINA,
        "blocking": False,
    }
    player.update(overrides)
    return player


def _human_player(player_id="human-1", **overrides):
    player = {
        "id": player_id,
        "position": {"x": 400, "y": 400},
        "blocking": False,
    }
    player.update(overrides)
    return player


class TestBotAvatar:
    def test_bot_id_and_avatar_are_defined(self):
        assert BOT_ID == "ai-bot"
        assert BOT_AVATAR["username"]


class TestTickWithNoBotPresent:
    def test_returns_none_when_bot_not_in_players_list(self):
        bot = AIBot()
        result = bot.tick(now_s=0.0, players=[_human_player()])
        assert result is None


class TestTickWithNoOtherPlayers:
    def test_wanders_when_alone_in_room(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.uniform", lambda a, b: (a + b) / 2)
        player = _bot_player()
        result = bot.tick(now_s=0.0, players=[player])
        assert result is None
        assert player["targetPosition"] is not None
        assert bot.wander_target == player["targetPosition"]

    def test_does_not_repick_wander_target_before_interval_elapses(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.uniform", lambda a, b: (a + b) / 2)
        player = _bot_player()
        bot.tick(now_s=0.0, players=[player])
        first_target = bot.wander_target
        bot.tick(now_s=1.0, players=[player])
        assert bot.wander_target == first_target


class TestTickStunned:
    def test_returns_none_and_clears_target_when_stunned(self):
        bot = AIBot()
        bot.stunned_until_ms = 5_000.0
        player = _bot_player(targetPosition={"x": 1, "y": 1})
        result = bot.tick(now_s=1.0, players=[player, _human_player()])
        assert result is None
        assert player["targetPosition"] is None

    def test_attacks_again_once_stun_expires(self, monkeypatch):
        bot = AIBot()
        bot.stunned_until_ms = 1_000.0
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 0.0)
        player = _bot_player()
        target = _human_player()
        result = bot.tick(now_s=1.0, players=[player, target])
        assert result is not None


class TestTickChat:
    def test_sets_pending_chat_when_target_is_close_and_interval_elapsed(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.choice", lambda seq: seq[0])
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 1.0)
        player = _bot_player()
        target = _human_player(position={"x": 450, "y": 400})
        bot.tick(now_s=100.0, players=[player, target])
        assert bot.pending_chat is not None

    def test_does_not_chat_again_immediately_after_chatting(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.choice", lambda seq: seq[0])
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 1.0)
        player = _bot_player()
        target = _human_player(position={"x": 450, "y": 400})
        bot.tick(now_s=100.0, players=[player, target])
        bot.pending_chat = None
        bot.tick(now_s=100.5, players=[player, target])
        assert bot.pending_chat is None


class TestTickApproachAndAttack:
    def test_approaches_target_when_outside_attack_range(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 1.0)
        player = _bot_player(position={"x": 400, "y": 400})
        target = _human_player(position={"x": 500, "y": 400})
        bot.tick(now_s=1.0, players=[player, target])
        assert player["targetPosition"] == target["position"]

    def test_stops_approaching_once_within_attack_range(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 1.0)
        player = _bot_player(position={"x": 400, "y": 400})
        target = _human_player(position={"x": 420, "y": 400})
        bot.tick(now_s=1.0, players=[player, target])
        assert player["targetPosition"] is None
        assert player["direction"] == {"x": 0, "y": 0}

    def test_attacks_with_punch_when_kick_probability_roll_fails(self, monkeypatch):
        bot = AIBot()
        # random.random() drives both the block roll and the kick-vs-punch roll;
        # a value >= _KICK_PROB (0.35) means punch is selected.
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 0.99)
        player = _bot_player(position={"x": 400, "y": 400})
        target = _human_player(position={"x": 410, "y": 400})
        result = bot.tick(now_s=1.0, players=[player, target])
        assert result is not None
        assert result["type"] == "punch"
        assert result["targetId"] == target["id"]

    def test_attacks_with_kick_when_kick_probability_roll_succeeds(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 0.0)
        player = _bot_player(position={"x": 400, "y": 400})
        target = _human_player(position={"x": 410, "y": 400})
        result = bot.tick(now_s=1.0, players=[player, target])
        assert result is not None
        assert result["type"] == "kick"

    def test_attack_deducts_stamina_cost(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 0.99)
        player = _bot_player(position={"x": 400, "y": 400}, stamina=MAX_STAMINA)
        target = _human_player(position={"x": 410, "y": 400})
        bot.tick(now_s=1.0, players=[player, target])
        assert player["stamina"] == MAX_STAMINA - ATTACK_TYPES["punch"]["stamina_cost"]

    def test_does_not_attack_when_stamina_insufficient(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 0.99)
        player = _bot_player(position={"x": 400, "y": 400}, stamina=1.0)
        target = _human_player(position={"x": 410, "y": 400})
        result = bot.tick(now_s=1.0, players=[player, target])
        assert result is None

    def test_does_not_attack_again_before_cooldown_elapses(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 0.99)
        player = _bot_player(position={"x": 400, "y": 400})
        target = _human_player(position={"x": 410, "y": 400})
        first = bot.tick(now_s=1.0, players=[player, target])
        assert first is not None
        second = bot.tick(now_s=1.1, players=[player, target])
        assert second is None

    def test_does_not_attack_a_stunned_target(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 0.99)
        player = _bot_player(position={"x": 400, "y": 400})
        target = _human_player(position={"x": 410, "y": 400}, stunnedUntil=999_999_999.0)
        result = bot.tick(now_s=1.0, players=[player, target])
        assert result is None

    def test_damage_reflects_target_blocking_state(self, monkeypatch):
        bot = AIBot()
        monkeypatch.setattr("server.game.ai_bot.random.random", lambda: 0.99)
        player = _bot_player(position={"x": 400, "y": 400})
        target = _human_player(position={"x": 410, "y": 400}, blocking=True)
        result = bot.tick(now_s=1.0, players=[player, target])
        assert result["blocked"] is True
        assert result["damage"] < ATTACK_TYPES["punch"]["damage"]


class TestOnHit:
    def test_on_hit_sets_stunned_until_in_the_future(self):
        bot = AIBot()
        bot.on_hit(now_ms=10_000.0)
        assert bot.stunned_until_ms > 10_000.0
