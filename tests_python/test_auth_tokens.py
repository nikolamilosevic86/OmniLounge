"""Unit tests for server/auth/tokens.py: JWT access/refresh token issuance
and validation (design doc §17, §7.1.2/7.1.8)."""

import time

import pytest

from server.auth.tokens import (
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)

SECRET = "test-secret-key-at-least-32-characters-long"


class TestCreateAndDecodeAccessToken:
    def test_decodes_back_to_the_same_claims(self):
        token = create_access_token(
            user_id="user-1", email="a@example.com", role="learner", session_id="sess-1",
            secret=SECRET, expires_in_seconds=1800,
        )
        claims = decode_token(token, secret=SECRET)
        assert claims["sub"] == "user-1"
        assert claims["email"] == "a@example.com"
        assert claims["role"] == "learner"
        assert claims["session_id"] == "sess-1"
        assert claims["type"] == "access"

    def test_includes_issuer_and_expiry_claims(self):
        token = create_access_token(
            user_id="user-1", email="a@example.com", role="learner", session_id="sess-1",
            secret=SECRET, expires_in_seconds=1800,
        )
        claims = decode_token(token, secret=SECRET)
        assert claims["iss"] == "omnilaunge"
        assert claims["exp"] > claims["iat"]

    def test_expired_token_raises_token_expired_error(self):
        token = create_access_token(
            user_id="user-1", email="a@example.com", role="learner", session_id="sess-1",
            secret=SECRET, expires_in_seconds=-1,
        )
        with pytest.raises(TokenExpiredError):
            decode_token(token, secret=SECRET)

    def test_tampered_signature_is_rejected(self):
        token = create_access_token(
            user_id="user-1", email="a@example.com", role="learner", session_id="sess-1",
            secret=SECRET, expires_in_seconds=1800,
        )
        # Flip a character in the middle of the signature segment, not the
        # very last character of the token: base64url's final character can
        # encode fewer than 6 bits (the rest are padding zeros), so some
        # substitutions there decode to the exact same bytes and would make
        # this test flaky.
        middle = len(token) // 2
        replacement = "A" if token[middle] != "A" else "B"
        tampered = token[:middle] + replacement + token[middle + 1:]
        with pytest.raises(InvalidTokenError):
            decode_token(tampered, secret=SECRET)

    def test_wrong_secret_is_rejected(self):
        token = create_access_token(
            user_id="user-1", email="a@example.com", role="learner", session_id="sess-1",
            secret=SECRET, expires_in_seconds=1800,
        )
        with pytest.raises(InvalidTokenError):
            decode_token(token, secret="a-completely-different-secret-value")

    def test_garbage_input_is_rejected(self):
        with pytest.raises(InvalidTokenError):
            decode_token("not.a.jwt", secret=SECRET)

    def test_wrong_issuer_is_rejected(self):
        token = create_access_token(
            user_id="user-1", email="a@example.com", role="learner", session_id="sess-1",
            secret=SECRET, expires_in_seconds=1800, issuer="someone-else",
        )
        with pytest.raises(InvalidTokenError):
            decode_token(token, secret=SECRET)


class TestRefreshToken:
    def test_refresh_token_has_type_refresh(self):
        token = create_refresh_token(
            user_id="user-1", session_id="sess-1", secret=SECRET, expires_in_seconds=604800,
        )
        claims = decode_token(token, secret=SECRET)
        assert claims["type"] == "refresh"
        assert claims["sub"] == "user-1"
        assert claims["session_id"] == "sess-1"

    def test_access_token_and_refresh_token_are_not_interchangeable(self):
        """decode_token(..., expected_type=...) must reject a refresh token
        presented where an access token is required, and vice versa --
        otherwise a stolen long-lived refresh token could be replayed
        directly against protected endpoints."""
        refresh = create_refresh_token(
            user_id="user-1", session_id="sess-1", secret=SECRET, expires_in_seconds=604800,
        )
        with pytest.raises(InvalidTokenError):
            decode_token(refresh, secret=SECRET, expected_type="access")

        access = create_access_token(
            user_id="user-1", email="a@example.com", role="learner", session_id="sess-1",
            secret=SECRET, expires_in_seconds=1800,
        )
        with pytest.raises(InvalidTokenError):
            decode_token(access, secret=SECRET, expected_type="refresh")


class TestHashToken:
    def test_same_token_hashes_the_same_way(self):
        assert hash_token("abc.def.ghi") == hash_token("abc.def.ghi")

    def test_different_tokens_hash_differently(self):
        assert hash_token("abc.def.ghi") != hash_token("abc.def.xyz")

    def test_hash_does_not_contain_the_raw_token(self):
        # The DB only ever stores the hash (design doc §6.2): a leaked DB
        # row must not let an attacker reconstruct a usable token.
        digest = hash_token("super-secret-token-value")
        assert "super-secret-token-value" not in digest
