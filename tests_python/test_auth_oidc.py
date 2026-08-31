"""Unit tests for server/auth/oidc.py: OIDC id_token verification via a
provider's JWKS endpoint (design doc §4.3, §4.4, §10.3).

Builds a real RSA keypair and a matching JWKS document locally so these
tests never make a network call to a real identity provider.
"""

import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from server.auth.oidc import IdTokenVerificationError, JwksUnavailableError, verify_id_token

ISSUER = "https://login.example.com/tenant-id/v2.0"
AUDIENCE = "test-client-id"
KID = "test-key-1"


def _make_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk["kid"] = KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return private_key, {"keys": [jwk]}


PRIVATE_KEY, JWKS = _make_keypair()


def _make_id_token(*, audience=AUDIENCE, issuer=ISSUER, exp_delta=3600, kid=KID, **extra_claims):
    now = int(time.time())
    claims = {
        "sub": "provider-user-1", "email": "alice@example.com", "name": "Alice",
        "iat": now, "exp": now + exp_delta, "aud": audience, "iss": issuer,
        **extra_claims,
    }
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256", headers={"kid": kid})


class _FakeTransport(httpx.AsyncBaseTransport):
    """Serves the local JWKS fixture for any request, instead of hitting the network."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=JWKS)


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_FakeTransport())


class TestVerifyIdToken:
    async def test_accepts_a_correctly_signed_token(self):
        token = _make_id_token()
        async with _http_client() as client:
            claims = await verify_id_token(
                token, jwks_uri="https://login.example.com/keys", audience=AUDIENCE, issuer=ISSUER,
                http_client=client,
            )
        assert claims["sub"] == "provider-user-1"
        assert claims["email"] == "alice@example.com"

    async def test_rejects_a_token_signed_with_a_different_key(self):
        other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(time.time())
        forged = jwt.encode(
            {"sub": "attacker", "iat": now, "exp": now + 3600, "aud": AUDIENCE, "iss": ISSUER},
            other_private_key, algorithm="RS256", headers={"kid": KID},
        )
        async with _http_client() as client:
            with pytest.raises(IdTokenVerificationError):
                await verify_id_token(
                    forged, jwks_uri="https://login.example.com/keys", audience=AUDIENCE, issuer=ISSUER,
                    http_client=client,
                )

    async def test_rejects_an_expired_token(self):
        token = _make_id_token(exp_delta=-3600)
        async with _http_client() as client:
            with pytest.raises(IdTokenVerificationError):
                await verify_id_token(
                    token, jwks_uri="https://login.example.com/keys", audience=AUDIENCE, issuer=ISSUER,
                    http_client=client,
                )

    async def test_rejects_a_token_with_the_wrong_audience(self):
        token = _make_id_token(audience="some-other-client-id")
        async with _http_client() as client:
            with pytest.raises(IdTokenVerificationError):
                await verify_id_token(
                    token, jwks_uri="https://login.example.com/keys", audience=AUDIENCE, issuer=ISSUER,
                    http_client=client,
                )

    async def test_rejects_a_token_with_the_wrong_issuer(self):
        token = _make_id_token(issuer="https://evil.example.com/")
        async with _http_client() as client:
            with pytest.raises(IdTokenVerificationError):
                await verify_id_token(
                    token, jwks_uri="https://login.example.com/keys", audience=AUDIENCE, issuer=ISSUER,
                    http_client=client,
                )

    async def test_rejects_a_token_with_an_unknown_kid(self):
        token = _make_id_token(kid="not-in-the-jwks")
        async with _http_client() as client:
            with pytest.raises(IdTokenVerificationError):
                await verify_id_token(
                    token, jwks_uri="https://login.example.com/keys", audience=AUDIENCE, issuer=ISSUER,
                    http_client=client,
                )

    async def test_rejects_a_malformed_token(self):
        async with _http_client() as client:
            with pytest.raises(IdTokenVerificationError):
                await verify_id_token(
                    "not-a-jwt-at-all", jwks_uri="https://login.example.com/keys", audience=AUDIENCE,
                    issuer=ISSUER, http_client=client,
                )

    async def test_rejects_an_unsigned_none_algorithm_token(self):
        """A token that claims alg=none must never be accepted, even though
        it would otherwise decode 'successfully' -- this is the classic
        JWT algorithm-confusion vulnerability."""
        now = int(time.time())
        claims = {"sub": "attacker", "iat": now, "exp": now + 3600, "aud": AUDIENCE, "iss": ISSUER}
        forged = jwt.encode(claims, key=None, algorithm="none", headers={"kid": KID})
        async with _http_client() as client:
            with pytest.raises(IdTokenVerificationError):
                await verify_id_token(
                    forged, jwks_uri="https://login.example.com/keys", audience=AUDIENCE, issuer=ISSUER,
                    http_client=client,
                )

    async def test_raises_jwks_unavailable_when_the_jwks_endpoint_is_unreachable(self):
        """Distinct from every other case above: the token itself might be
        perfectly valid, but a network failure fetching the provider's
        public keys must be reported as a different, more specific error
        so callers can tell "we couldn't check" from "we checked, and it's
        invalid"."""
        token = _make_id_token()

        class _UnreachableTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("connection refused", request=request)

        async with httpx.AsyncClient(transport=_UnreachableTransport()) as client:
            with pytest.raises(JwksUnavailableError):
                await verify_id_token(
                    token, jwks_uri="https://login.example.com/keys", audience=AUDIENCE, issuer=ISSUER,
                    http_client=client,
                )
