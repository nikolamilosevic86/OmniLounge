"""Tests for `server/game/combat.py` — PvP damage, stamina, cooldown, range,
and stun math. This module previously had zero test coverage even though it
directly governs combat outcomes (damage dealt, when attacks are permitted,
whether an attack lands, and stamina regeneration)."""

import pytest

from server.game.combat import (
    ATTACK_TYPES,
    BLOCK_REDUCTION,
    MAX_STAMINA,
    STUN_DURATION_MS,
    apply_hit,
    calculate_damage,
    can_attack,
    is_in_range,
    regen_stamina,
)


class TestCalculateDamage:
    def test_punch_deals_configured_damage_when_unblocked(self):
        assert calculate_damage("punch") == ATTACK_TYPES["punch"]["damage"]

    def test_kick_deals_configured_damage_when_unblocked(self):
        assert calculate_damage("kick") == ATTACK_TYPES["kick"]["damage"]

    def test_punch_damage_is_reduced_when_blocked(self):
        expected = round(ATTACK_TYPES["punch"]["damage"] * (1 - BLOCK_REDUCTION))
        assert calculate_damage("punch", blocked=True) == expected

    def test_kick_damage_is_reduced_when_blocked(self):
        expected = round(ATTACK_TYPES["kick"]["damage"] * (1 - BLOCK_REDUCTION))
        assert calculate_damage("kick", blocked=True) == expected

    def test_blocked_damage_is_strictly_less_than_unblocked(self):
        assert calculate_damage("punch", blocked=True) < calculate_damage("punch", blocked=False)
        assert calculate_damage("kick", blocked=True) < calculate_damage("kick", blocked=False)

    def test_unknown_attack_type_deals_zero_damage(self):
        assert calculate_damage("headbutt") == 0
        assert calculate_damage("headbutt", blocked=True) == 0


class TestCanAttack:
    def test_allows_attack_with_full_stamina_and_no_cooldown(self):
        assert can_attack(stamina=100, last_attack_ms=0, now_ms=10_000, attack_type="punch") is True

    def test_rejects_unknown_attack_type(self):
        assert can_attack(stamina=100, last_attack_ms=0, now_ms=10_000, attack_type="headbutt") is False

    def test_rejects_when_stamina_below_cost(self):
        cost = ATTACK_TYPES["kick"]["stamina_cost"]
        assert can_attack(stamina=cost - 1, last_attack_ms=0, now_ms=10_000, attack_type="kick") is False

    def test_allows_when_stamina_exactly_equals_cost(self):
        cost = ATTACK_TYPES["punch"]["stamina_cost"]
        assert can_attack(stamina=cost, last_attack_ms=0, now_ms=10_000, attack_type="punch") is True

    def test_rejects_when_still_within_cooldown(self):
        cooldown = ATTACK_TYPES["punch"]["cooldown_ms"]
        assert can_attack(stamina=100, last_attack_ms=1_000, now_ms=1_000 + cooldown - 1, attack_type="punch") is False

    def test_allows_once_cooldown_has_fully_elapsed(self):
        cooldown = ATTACK_TYPES["punch"]["cooldown_ms"]
        assert can_attack(stamina=100, last_attack_ms=1_000, now_ms=1_000 + cooldown, attack_type="punch") is True

    def test_rejects_while_stunned(self):
        assert can_attack(
            stamina=100, last_attack_ms=0, now_ms=10_000, attack_type="punch", stunned_until_ms=10_001,
        ) is False

    def test_allows_exactly_when_stun_expires(self):
        assert can_attack(
            stamina=100, last_attack_ms=0, now_ms=10_000, attack_type="punch", stunned_until_ms=10_000,
        ) is True


class TestIsInRange:
    def test_same_position_is_in_range(self):
        assert is_in_range({"x": 0, "y": 0}, {"x": 0, "y": 0}, "punch") is True

    def test_distance_within_range_is_in_range(self):
        cfg_range = ATTACK_TYPES["punch"]["range"]
        assert is_in_range({"x": 0, "y": 0}, {"x": cfg_range - 1, "y": 0}, "punch") is True

    def test_distance_beyond_range_is_out_of_range(self):
        cfg_range = ATTACK_TYPES["punch"]["range"]
        assert is_in_range({"x": 0, "y": 0}, {"x": cfg_range + 10, "y": 0}, "punch") is False

    def test_distance_exactly_at_range_boundary_is_in_range(self):
        cfg_range = ATTACK_TYPES["kick"]["range"]
        assert is_in_range({"x": 0, "y": 0}, {"x": cfg_range, "y": 0}, "kick") is True

    def test_unknown_attack_type_is_never_in_range(self):
        assert is_in_range({"x": 0, "y": 0}, {"x": 0, "y": 0}, "headbutt") is False

    def test_diagonal_distance_uses_euclidean_math(self):
        # 3-4-5 triangle: distance is exactly 5.
        assert is_in_range({"x": 0, "y": 0}, {"x": 3, "y": 4}, "punch") is True


class TestApplyHit:
    def test_reduces_stamina_by_damage(self):
        assert apply_hit(100, 20) == 80

    def test_clamps_to_zero_when_damage_exceeds_stamina(self):
        assert apply_hit(10, 50) == 0.0

    def test_zero_damage_leaves_stamina_unchanged(self):
        assert apply_hit(50, 0) == 50


class TestRegenStamina:
    def test_increases_stamina_over_time(self):
        assert regen_stamina(50, 1000) > 50

    def test_caps_at_max_stamina(self):
        assert regen_stamina(MAX_STAMINA, 10_000) == MAX_STAMINA

    def test_does_not_exceed_max_even_from_low_stamina_over_long_time(self):
        assert regen_stamina(0, 1_000_000) == MAX_STAMINA

    def test_zero_delta_leaves_stamina_unchanged(self):
        assert regen_stamina(42, 0) == 42


class TestStunDuration:
    def test_stun_duration_is_positive(self):
        assert STUN_DURATION_MS > 0
