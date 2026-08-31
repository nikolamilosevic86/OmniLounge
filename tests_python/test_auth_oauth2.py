"""Unit tests for server/auth/oauth2.py: PKCE helper, authorization URL
construction, code exchange, and provider-specific profile normalization
(design doc §4.3, §4.4, §10.3)."""

import base64
import hashlib

import httpx
import jwt
import pytest
import time
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from server.auth.oauth2 import (
    OAuth2Error,
    OAuth2ProviderSettings,
    OAuth2ProviderUnavailableError,
    build_authorization_url,
    generate_pkce_pair,
    resolve_provider_identity,
)

ISSUER = "https://login.example.com/tenant-id/v2.0"
AUDIENCE = "test-client-id"
KID = "test-key-1"


def _make_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = KID
    return private_key, {"keys": [jwk]}


PRIVATE_KEY, JWKS = _make_keypair()


def _make_id_token(**extra_claims):
    now = int(time.time())
    claims = {
        "sub": "provider-user-1", "email": "alice@example.com", "name": "Alice",
        "iat": now, "exp": now + 3600, "aud": AUDIENCE, "iss": ISSUER,
        **extra_claims,
    }
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})


class _ScriptedTransport(httpx.AsyncBaseTransport):
    """Replays a fixed sequence of responses keyed by request URL, so tests
    never make a real network call."""

    def __init__(self, responses: dict[str, httpx.Response]):
        self._responses = responses
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url).split("?")[0]
        if url not in self._responses:
            raise AssertionError(f"unexpected request to {url}")
        return self._responses[url]


class _UnreachableTransport(httpx.AsyncBaseTransport):
    """Simulates a network-level failure (DNS/timeout/connection refused)
    reaching every endpoint, instead of the provider returning a response."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)


def oidc_provider(**overrides) -> OAuth2ProviderSettings:
    defaults = dict(
        name="azure", provider_type="azure", client_id=AUDIENCE, client_secret="secret",
        redirect_uri="https://app.example.com/auth/callback/azure",
        authorization_endpoint="https://login.example.com/authorize",
        token_endpoint="https://login.example.com/token",
        jwks_uri="https://login.example.com/keys", issuer=ISSUER,
        scopes=["openid", "profile", "email"], label="Sign in with Microsoft",
    )
    defaults.update(overrides)
    return OAuth2ProviderSettings(**defaults)


class TestPkce:
    def test_generates_a_verifier_and_matching_s256_challenge(self):
        verifier, challenge = generate_pkce_pair()
        assert 43 <= len(verifier) <= 128
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
        assert challenge == expected

    def test_generates_different_pairs_each_time(self):
        pair1 = generate_pkce_pair()
        pair2 = generate_pkce_pair()
        assert pair1 != pair2


class TestBuildAuthorizationUrl:
    def test_includes_pkce_and_state_params(self):
        provider = oidc_provider()
        url = build_authorization_url(provider, state="abc123", code_challenge="chal456")
        assert url.startswith(provider.authorization_endpoint)
        assert "state=abc123" in url
        assert "code_challenge=chal456" in url
        assert "code_challenge_method=S256" in url
        assert f"client_id={provider.client_id}" in url
        assert "response_type=code" in url


class TestResolveProviderIdentityOidc:
    async def test_returns_a_normalized_identity_from_a_valid_id_token(self):
        provider = oidc_provider()
        id_token = _make_id_token()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={"access_token": "at", "id_token": id_token}),
            provider.jwks_uri: httpx.Response(200, json=JWKS),
        })
        async with httpx.AsyncClient(transport=transport) as client:
            identity = await resolve_provider_identity(
                provider, code="auth-code", code_verifier="verifier", http_client=client,
            )
        assert identity == {
            "provider_user_id": "provider-user-1", "email": "alice@example.com",
            "email_verified": True, "name": "Alice", "picture": None, "groups": [],
        }
        # PKCE verifier and authorization code must reach the token endpoint.
        token_request = transport.requests[0]
        body = token_request.content.decode()
        assert "code_verifier=verifier" in body
        assert "code=auth-code" in body

    async def test_raises_when_token_endpoint_returns_an_error(self):
        provider = oidc_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(400, json={"error": "invalid_grant"}),
        })
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(OAuth2Error):
                await resolve_provider_identity(provider, code="bad-code", code_verifier="v", http_client=client)

    async def test_raises_provider_unavailable_when_the_token_endpoint_is_unreachable(self):
        provider = oidc_provider()
        async with httpx.AsyncClient(transport=_UnreachableTransport()) as client:
            with pytest.raises(OAuth2ProviderUnavailableError):
                await resolve_provider_identity(provider, code="auth-code", code_verifier="v", http_client=client)

    async def test_raises_provider_unavailable_when_the_jwks_endpoint_is_unreachable(self):
        provider = oidc_provider()
        id_token = _make_id_token()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={"access_token": "at", "id_token": id_token}),
        })

        class _MixedTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                url = str(request.url).split("?")[0]
                if url == provider.jwks_uri:
                    raise httpx.ConnectError("connection refused", request=request)
                return await transport.handle_async_request(request)

        async with httpx.AsyncClient(transport=_MixedTransport()) as client:
            with pytest.raises(OAuth2ProviderUnavailableError):
                await resolve_provider_identity(provider, code="auth-code", code_verifier="v", http_client=client)

    async def test_propagates_an_explicit_unverified_email_claim(self):
        provider = oidc_provider()
        id_token = _make_id_token(email_verified=False)
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={"access_token": "at", "id_token": id_token}),
            provider.jwks_uri: httpx.Response(200, json=JWKS),
        })
        async with httpx.AsyncClient(transport=transport) as client:
            identity = await resolve_provider_identity(
                provider, code="auth-code", code_verifier="verifier", http_client=client,
            )
        assert identity["email_verified"] is False

    async def test_propagates_the_groups_claim(self):
        provider = oidc_provider()
        id_token = _make_id_token(groups=["group-a", "group-b"])
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={"access_token": "at", "id_token": id_token}),
            provider.jwks_uri: httpx.Response(200, json=JWKS),
        })
        async with httpx.AsyncClient(transport=transport) as client:
            identity = await resolve_provider_identity(
                provider, code="auth-code", code_verifier="verifier", http_client=client,
            )
        assert identity["groups"] == ["group-a", "group-b"]

    async def test_raises_when_no_id_token_is_returned(self):
        provider = oidc_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={"access_token": "at"}),
        })
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(OAuth2Error):
                await resolve_provider_identity(provider, code="auth-code", code_verifier="v", http_client=client)

    async def test_raises_when_id_token_signature_is_invalid(self):
        provider = oidc_provider()
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(time.time())
        forged = jwt.encode(
            {"sub": "attacker", "iat": now, "exp": now + 3600, "aud": AUDIENCE, "iss": ISSUER},
            other_key, algorithm="RS256", headers={"kid": KID},
        )
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={"access_token": "at", "id_token": forged}),
            provider.jwks_uri: httpx.Response(200, json=JWKS),
        })
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(OAuth2Error):
                await resolve_provider_identity(provider, code="auth-code", code_verifier="v", http_client=client)


class TestResolveProviderIdentityGithub:
    def github_provider(self, **overrides):
        return oidc_provider(
            name="github", provider_type="github", jwks_uri=None, issuer=None,
            scopes=["read:user", "user:email"], **overrides,
        )

    async def test_uses_the_public_email_from_the_user_endpoint_when_present(self):
        provider = self.github_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={"access_token": "gh-token"}),
            "https://api.github.com/user": httpx.Response(
                200, json={"id": 42, "login": "alice", "name": "Alice", "avatar_url": "http://x/a.png",
                           "email": "alice@example.com"},
            ),
        })
        async with httpx.AsyncClient(transport=transport) as client:
            identity = await resolve_provider_identity(provider, code="c", code_verifier="v", http_client=client)
        assert identity == {
            "provider_user_id": "42", "email": "alice@example.com", "email_verified": True,
            "name": "Alice", "picture": "http://x/a.png", "groups": [],
        }

    async def test_falls_back_to_the_verified_primary_email_endpoint(self):
        provider = self.github_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={"access_token": "gh-token"}),
            "https://api.github.com/user": httpx.Response(
                200, json={"id": 42, "login": "alice", "name": None, "avatar_url": None, "email": None},
            ),
            "https://api.github.com/user/emails": httpx.Response(
                200, json=[
                    {"email": "secondary@example.com", "primary": False, "verified": True},
                    {"email": "primary@example.com", "primary": True, "verified": True},
                ],
            ),
        })
        async with httpx.AsyncClient(transport=transport) as client:
            identity = await resolve_provider_identity(provider, code="c", code_verifier="v", http_client=client)
        assert identity["email"] == "primary@example.com"

    async def test_raises_when_github_token_exchange_omits_access_token(self):
        provider = self.github_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={}),
        })
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(OAuth2Error):
                await resolve_provider_identity(provider, code="c", code_verifier="v", http_client=client)

    async def test_raises_provider_unavailable_when_the_github_api_is_unreachable(self):
        provider = self.github_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(200, json={"access_token": "gh-token"}),
        })

        class _MixedTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                if str(request.url) == "https://api.github.com/user":
                    raise httpx.ConnectError("connection refused", request=request)
                return await transport.handle_async_request(request)

        async with httpx.AsyncClient(transport=_MixedTransport()) as client:
            with pytest.raises(OAuth2ProviderUnavailableError):
                await resolve_provider_identity(provider, code="c", code_verifier="v", http_client=client)
