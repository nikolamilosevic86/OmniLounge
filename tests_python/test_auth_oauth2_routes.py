"""Tests for server/auth/oauth2_routes.py: the /api/auth/oauth2/* HTTP
endpoints (design doc §7.1.6, §7.1.7)."""

import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from server.auth import dependencies, oauth2_routes
from server.auth.errors import AuthHTTPError, auth_http_error_handler
from server.auth.oauth2 import OAuth2ProviderSettings
from tests_python.test_auth_routes import make_service

ISSUER = "https://login.example.com/tenant-id/v2.0"
AUDIENCE = "test-client-id"
KID = "test-key-1"


def _make_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk["kid"] = KID
    return private_key, {"keys": [jwk]}


PRIVATE_KEY, JWKS = _make_keypair()


def _make_id_token(**extra):
    now = int(time.time())
    claims = {
        "sub": "azure-sub-1", "email": "alice@example.com", "name": "Alice",
        "iat": now, "exp": now + 3600, "aud": AUDIENCE, "iss": ISSUER, **extra,
    }
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})


def azure_provider() -> OAuth2ProviderSettings:
    return OAuth2ProviderSettings(
        name="azure", provider_type="azure", client_id=AUDIENCE, client_secret="secret",
        redirect_uri="https://app.example.com/auth/callback/azure",
        authorization_endpoint="https://login.example.com/authorize",
        token_endpoint="https://login.example.com/token",
        jwks_uri="https://login.example.com/keys", issuer=ISSUER,
        scopes=["openid", "profile", "email"], label="Sign in with Microsoft",
    )


class _ScriptedTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: dict[str, httpx.Response]):
        self._responses = responses

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        if url not in self._responses:
            raise AssertionError(f"unexpected request to {url}")
        return self._responses[url]


class TestAuthorizeEndpoint:
    async def test_redirects_to_the_providers_authorization_endpoint(self):
        dependencies.set_oauth2_providers({"azure": azure_provider()})
        response = await oauth2_routes.oauth2_authorize(
            provider="azure", state="abc", code_challenge="chal", providers=dependencies.get_oauth2_providers(),
        )
        assert response.status_code == 302
        assert response.headers["location"].startswith("https://login.example.com/authorize")
        assert "state=abc" in response.headers["location"]

    async def test_unknown_provider_raises_404(self):
        dependencies.set_oauth2_providers({})
        with pytest.raises(AuthHTTPError) as exc_info:
            await oauth2_routes.oauth2_authorize(
                provider="azure", state="abc", code_challenge="chal", providers=dependencies.get_oauth2_providers(),
            )
        assert exc_info.value.status_code == 404


class TestCallbackEndpoint:
    async def test_successful_callback_returns_tokens_for_a_new_user(self):
        service = make_service()
        provider = azure_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(
                200, json={"access_token": "at", "id_token": _make_id_token()},
            ),
            provider.jwks_uri: httpx.Response(200, json=JWKS),
        })
        async with httpx.AsyncClient(transport=transport) as http_client:
            result = await oauth2_routes.oauth2_callback(
                provider="azure",
                body=oauth2_routes.OAuth2CallbackBody(code="c", state="s", codeVerifier="v"),
                client_ip="1.2.3.4",
                providers={"azure": provider},
                service=service,
                http_client=http_client,
            )
        assert result["is_new_user"] is True
        assert result["user"]["email"] == "alice@example.com"
        assert result["access_token"]

    async def test_unknown_provider_raises_404(self):
        service = make_service()
        async with httpx.AsyncClient() as http_client:
            with pytest.raises(AuthHTTPError) as exc_info:
                await oauth2_routes.oauth2_callback(
                    provider="azure",
                    body=oauth2_routes.OAuth2CallbackBody(code="c", state="s", codeVerifier="v"),
                    client_ip=None, providers={}, service=service, http_client=http_client,
                )
        assert exc_info.value.status_code == 404

    async def test_provider_error_maps_to_401(self):
        service = make_service()
        provider = azure_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(400, json={"error": "invalid_grant"}),
        })
        async with httpx.AsyncClient(transport=transport) as http_client:
            with pytest.raises(AuthHTTPError) as exc_info:
                await oauth2_routes.oauth2_callback(
                    provider="azure",
                    body=oauth2_routes.OAuth2CallbackBody(code="bad", state="s", codeVerifier="v"),
                    client_ip=None, providers={"azure": provider}, service=service, http_client=http_client,
                )
        assert exc_info.value.status_code == 401

    async def test_unreachable_provider_maps_to_503(self):
        service = make_service()
        provider = azure_provider()

        class _UnreachableTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("connection refused", request=request)

        async with httpx.AsyncClient(transport=_UnreachableTransport()) as http_client:
            with pytest.raises(AuthHTTPError) as exc_info:
                await oauth2_routes.oauth2_callback(
                    provider="azure",
                    body=oauth2_routes.OAuth2CallbackBody(code="c", state="s", codeVerifier="v"),
                    client_ip=None, providers={"azure": provider}, service=service, http_client=http_client,
                )
        assert exc_info.value.status_code == 503
        assert exc_info.value.error == "PROVIDER_UNAVAILABLE"

    async def test_missing_email_from_provider_maps_to_400(self):
        service = make_service()
        provider = azure_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(
                200, json={"access_token": "at", "id_token": _make_id_token(email=None)},
            ),
            provider.jwks_uri: httpx.Response(200, json=JWKS),
        })
        async with httpx.AsyncClient(transport=transport) as http_client:
            with pytest.raises(AuthHTTPError) as exc_info:
                await oauth2_routes.oauth2_callback(
                    provider="azure",
                    body=oauth2_routes.OAuth2CallbackBody(code="c", state="s", codeVerifier="v"),
                    client_ip=None, providers={"azure": provider}, service=service, http_client=http_client,
                )
        assert exc_info.value.status_code == 400

    async def test_group_restricted_provider_rejects_a_non_member_with_403(self):
        service = make_service()
        provider = azure_provider()
        provider.allowed_groups = ["required-group"]
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(
                200, json={"access_token": "at", "id_token": _make_id_token(groups=["other-group"])},
            ),
            provider.jwks_uri: httpx.Response(200, json=JWKS),
        })
        async with httpx.AsyncClient(transport=transport) as http_client:
            with pytest.raises(AuthHTTPError) as exc_info:
                await oauth2_routes.oauth2_callback(
                    provider="azure",
                    body=oauth2_routes.OAuth2CallbackBody(code="c", state="s", codeVerifier="v"),
                    client_ip=None, providers={"azure": provider}, service=service, http_client=http_client,
                )
        assert exc_info.value.status_code == 403


class TestAppWiring:
    def test_authorize_and_callback_are_reachable_over_http(self):
        service = make_service()
        provider = azure_provider()
        transport = _ScriptedTransport({
            provider.token_endpoint: httpx.Response(
                200, json={"access_token": "at", "id_token": _make_id_token()},
            ),
            provider.jwks_uri: httpx.Response(200, json=JWKS),
        })

        app = FastAPI()
        app.add_exception_handler(AuthHTTPError, auth_http_error_handler)
        app.include_router(oauth2_routes.router)
        dependencies.set_auth_service(service)
        dependencies.set_oauth2_providers({"azure": provider})
        dependencies.set_oauth2_http_client(httpx.AsyncClient(transport=transport))
        client = TestClient(app)

        authorize_resp = client.get(
            "/api/auth/oauth2/authorize/azure", params={"state": "s", "code_challenge": "c"},
            follow_redirects=False,
        )
        assert authorize_resp.status_code == 302

        callback_resp = client.post(
            "/api/auth/oauth2/callback/azure", json={"code": "c", "state": "s", "codeVerifier": "v"},
        )
        assert callback_resp.status_code == 200
        assert callback_resp.json()["access_token"]
