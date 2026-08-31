"""Unit tests for server/auth/passwords.py: hashing and password-strength
validation. Pure functions, no DB/network, so these run instantly."""

import pytest

from server.auth.passwords import (
    generate_temporary_password,
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
)


class TestHashAndVerify:
    def test_hash_is_not_the_plaintext(self):
        digest = hash_password("CorrectHorseBattery1!")
        assert digest != "CorrectHorseBattery1!"

    def test_verify_accepts_the_correct_password(self):
        digest = hash_password("CorrectHorseBattery1!")
        assert verify_password("CorrectHorseBattery1!", digest) is True

    def test_verify_rejects_a_wrong_password(self):
        digest = hash_password("CorrectHorseBattery1!")
        assert verify_password("WrongPassword1!", digest) is False

    def test_hash_is_salted_so_two_hashes_of_the_same_password_differ(self):
        first = hash_password("CorrectHorseBattery1!")
        second = hash_password("CorrectHorseBattery1!")
        assert first != second

    def test_verify_never_raises_on_a_malformed_stored_hash(self):
        # A corrupted/truncated hash (e.g. from a botched migration) must be
        # treated as "does not match", never crash the login endpoint.
        assert verify_password("anything", "not-a-real-bcrypt-hash") is False

    def test_verify_rejects_empty_password_against_real_hash(self):
        digest = hash_password("CorrectHorseBattery1!")
        assert verify_password("", digest) is False

    def test_hash_password_rejects_empty_string(self):
        with pytest.raises(ValueError):
            hash_password("")


class TestNeedsRehash:
    def test_false_for_a_freshly_hashed_password(self):
        digest = hash_password("CorrectHorseBattery1!")
        assert needs_rehash(digest) is False

    def test_true_for_a_hash_using_a_lower_cost_factor(self):
        import bcrypt

        old_digest = bcrypt.hashpw(b"CorrectHorseBattery1!", bcrypt.gensalt(rounds=4)).decode("utf-8")
        assert needs_rehash(old_digest) is True


class TestValidatePasswordStrength:
    def test_accepts_a_strong_password(self):
        result = validate_password_strength("Tr0ub4dor&3!")
        assert result.valid is True
        assert result.errors == []

    def test_rejects_password_shorter_than_minimum_length(self):
        result = validate_password_strength("Ab1!", min_length=8)
        assert result.valid is False
        assert any("length" in e.lower() for e in result.errors)

    def test_rejects_missing_uppercase(self):
        result = validate_password_strength("lowercase1!")
        assert result.valid is False
        assert any("uppercase" in e.lower() for e in result.errors)

    def test_rejects_missing_lowercase(self):
        result = validate_password_strength("UPPERCASE1!")
        assert result.valid is False
        assert any("lowercase" in e.lower() for e in result.errors)

    def test_rejects_missing_digit(self):
        result = validate_password_strength("NoDigitsHere!")
        assert result.valid is False
        assert any("digit" in e.lower() for e in result.errors)

    def test_rejects_missing_special_character(self):
        result = validate_password_strength("NoSpecialChar1")
        assert result.valid is False
        assert any("special" in e.lower() for e in result.errors)

    def test_reports_every_violated_rule_at_once(self):
        result = validate_password_strength("short")
        assert result.valid is False
        assert len(result.errors) >= 3

    def test_rules_are_individually_toggleable(self):
        result = validate_password_strength(
            "alllowercase",
            require_uppercase=False,
            require_digits=False,
            require_special=False,
        )
        assert result.valid is True

    def test_rejects_a_password_found_on_the_common_password_blocklist(self):
        result = validate_password_strength("Password123!", block_common=True)
        assert result.valid is False
        assert any("common" in e.lower() for e in result.errors)

    def test_common_password_check_is_case_insensitive(self):
        result = validate_password_strength("PASSWORD123!", block_common=True)
        assert result.valid is False

    def test_rejects_password_containing_the_username(self):
        result = validate_password_strength("Alice12345!", username="alice")
        assert result.valid is False
        assert any("username" in e.lower() for e in result.errors)

    def test_accepts_password_when_username_not_provided(self):
        result = validate_password_strength("SomeAlice123!")
        assert result.valid is True

    def test_enforces_a_maximum_length_to_avoid_bcrypts_72_byte_truncation(self):
        # bcrypt silently ignores bytes past 72 -- a 200-char password would
        # otherwise "work" but only the first 72 bytes actually matter,
        # which is a footgun worth rejecting explicitly instead.
        result = validate_password_strength("A1!" + "a" * 100)
        assert result.valid is False
        assert any("72" in e or "long" in e.lower() for e in result.errors)

class TestGenerateTemporaryPassword:
    def test_generates_a_password_that_passes_the_default_strength_policy(self):
        password = generate_temporary_password()
        assert validate_password_strength(password).valid is True

    def test_generates_a_different_password_every_time(self):
        assert generate_temporary_password() != generate_temporary_password()

    def test_respects_a_custom_length(self):
        assert len(generate_temporary_password(length=20)) == 20