"""Tests for server/auth/routes.py: the /api/auth/* HTTP endpoints.

Most cases call the route handler functions directly with already-resolved
dependency values (matching the direct-call convention already used for
FastAPI handlers in tests_python/test_main_metrics.py), which is fast and
exercises the exact same request/response mapping code as real traffic.
A handful of TestClient-based tests at the bottom prove the actual ASGI
wiring (header parsing, exception-handler registration, path routing)
works end-to-end.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import dependencies, routes
from server.auth.config import AuthConfig, PasswordPolicy, SessionConfig
from server.auth.errors import AuthHTTPError, auth_http_error_handler
from server.auth.service import AuthService
from server.game.rate_limiter import SlidingWindowRateLimiter
from tests_python.test_auth_service import FakeUserRepo

SECRET = "test-secret-key-at-least-32-characters-long"
NOW_MS = 1_000_000_000.0


def make_service(**overrides) -> AuthService:
    config = AuthConfig(
        jwt_secret_key=SECRET,
        enable_local_registration=overrides.get("enable_local_registration", True),
        require_email_verification=overrides.get("require_email_verification", False),
        allow_guest_access=overrides.get("allow_guest_access", True),
        password_policy=PasswordPolicy(min_length=8),
        session_config=SessionConfig(access_token_expire_minutes=30, refresh_token_expire_days=7),
    )
    return AuthService(
        repo=FakeUserRepo(), config=config,
        registration_rate_limiter=SlidingWindowRateLimiter(max_requests=10, window_ms=3_600_000),
        login_rate_limiter=SlidingWindowRateLimiter(max_requests=10, window_ms=3_600_000),
    )


class TestRegisterEndpoint:
    async def test_successful_registration_returns_201_payload(self):
        service = make_service()
        body = routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A")
        result = await routes.register(body, client_ip="1.2.3.4", service=service)
        assert result["email"] == "a@example.com"
        assert "requires_avatar" in result

    async def test_duplicate_email_raises_409(self):
        service = make_service()
        body = routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A")
        await routes.register(body, client_ip=None, service=service)
        with pytest.raises(AuthHTTPError) as exc_info:
            await routes.register(body, client_ip=None, service=service)
        assert exc_info.value.status_code == 409
        assert exc_info.value.error == "EMAIL_TAKEN"

    async def test_weak_password_raises_400_with_field_errors(self):
        service = make_service()
        body = routes.RegisterRequest(email="b@example.com", password="weak", displayName="B")
        with pytest.raises(AuthHTTPError) as exc_info:
            await routes.register(body, client_ip=None, service=service)
        assert exc_info.value.status_code == 400
        assert exc_info.value.error == "WEAK_PASSWORD"
        assert exc_info.value.details["errors"]

    async def test_registration_disabled_raises_403(self):
        service = make_service(enable_local_registration=False)
        body = routes.RegisterRequest(email="c@example.com", password="Str0ngPass!", displayName="C")
        with pytest.raises(AuthHTTPError) as exc_info:
            await routes.register(body, client_ip=None, service=service)
        assert exc_info.value.status_code == 403
        assert exc_info.value.error == "REGISTRATION_DISABLED"


class TestLoginEndpoint:
    async def test_successful_login_returns_tokens(self):
        service = make_service()
        await routes.register(
            routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A"),
            client_ip=None, service=service,
        )
        result = await routes.login(
            routes.LoginRequest(emailOrUsername="a@example.com", password="Str0ngPass!"),
            client_ip="9.8.7.6", service=service,
        )
        assert result["access_token"]
        assert result["user"]["email"] == "a@example.com"

    async def test_wrong_password_raises_401(self):
        service = make_service()
        await routes.register(
            routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A"),
            client_ip=None, service=service,
        )
        with pytest.raises(AuthHTTPError) as exc_info:
            await routes.login(
                routes.LoginRequest(emailOrUsername="a@example.com", password="wrong"),
                client_ip=None, service=service,
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.error == "INVALID_CREDENTIALS"

    async def test_unverified_email_raises_403(self):
        service = make_service(require_email_verification=True)
        await routes.register(
            routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A"),
            client_ip=None, service=service,
        )
        with pytest.raises(AuthHTTPError) as exc_info:
            await routes.login(
                routes.LoginRequest(emailOrUsername="a@example.com", password="Str0ngPass!"),
                client_ip=None, service=service,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.error == "EMAIL_NOT_VERIFIED"


class TestMeAndProvidersEndpoints:
    async def test_me_returns_the_current_user(self):
        user = {
            "id": "u1", "email": "a@example.com", "role": "learner",
            "displayName": "A", "requiresPasswordChange": False,
        }
        result = await routes.get_me(user=user)
        assert result["email"] == "a@example.com"

    async def test_providers_reports_local_login_status(self):
        service = make_service()
        result = await routes.get_providers(service=service, oauth2_providers={})
        assert result["local_login_enabled"] is True
        assert result["oauth2_providers"] == []
        assert result["allow_guest_access"] is True

    async def test_providers_reports_guest_access_disabled(self):
        service = make_service(allow_guest_access=False)
        result = await routes.get_providers(service=service, oauth2_providers={})
        assert result["allow_guest_access"] is False

    async def test_providers_reports_configured_oauth2_providers(self):
        from server.auth.oauth2 import OAuth2ProviderSettings

        service = make_service()
        azure = OAuth2ProviderSettings(
            name="azure", provider_type="azure", client_id="c", client_secret="s",
            redirect_uri="https://app.example.com/auth/callback/azure",
            authorization_endpoint="https://login.example.com/authorize",
            token_endpoint="https://login.example.com/token",
            label="Sign in with Microsoft",
        )
        result = await routes.get_providers(service=service, oauth2_providers={"azure": azure})
        assert result["oauth2_providers"] == [
            {"name": "azure", "label": "Sign in with Microsoft", "authorize_url": "/api/auth/oauth2/authorize/azure"},
        ]


class TestRefreshAndLogoutEndpoints:
    async def _login(self, service):
        await routes.register(
            routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A"),
            client_ip=None, service=service,
        )
        return await routes.login(
            routes.LoginRequest(emailOrUsername="a@example.com", password="Str0ngPass!"),
            client_ip=None, service=service,
        )

    async def test_refresh_returns_a_new_access_token(self):
        service = make_service()
        logged_in = await self._login(service)
        result = await routes.refresh(
            routes.RefreshRequest(refreshToken=logged_in["refresh_token"]), service=service,
        )
        assert result["access_token"]

    async def test_refresh_with_garbage_token_raises_401(self):
        service = make_service()
        with pytest.raises(AuthHTTPError) as exc_info:
            await routes.refresh(routes.RefreshRequest(refreshToken="not-a-real-token"), service=service)
        assert exc_info.value.status_code == 401

    async def test_logout_revokes_the_session(self):
        service = make_service()
        logged_in = await self._login(service)
        result = await routes.logout(authorization=f"Bearer {logged_in['access_token']}", service=service)
        assert result["message"]
        with pytest.raises(AuthHTTPError):
            await routes.refresh(routes.RefreshRequest(refreshToken=logged_in["refresh_token"]), service=service)


class TestPasswordResetEndpoints:
    async def test_request_always_returns_200_even_for_unknown_email(self):
        service = make_service()
        result = await routes.request_password_reset(
            routes.PasswordResetRequestBody(email="nobody@example.com"), service=service,
        )
        assert "message" in result

    async def test_confirm_with_bad_token_raises_400(self):
        service = make_service()
        with pytest.raises(AuthHTTPError) as exc_info:
            await routes.confirm_password_reset(
                routes.PasswordResetConfirmBody(token="garbage", newPassword="NewStr0ngPass!"), service=service,
            )
        assert exc_info.value.status_code == 400

    async def test_confirm_with_a_valid_token_resets_the_password(self):
        service = make_service()
        await routes.register(
            routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A"),
            client_ip=None, service=service,
        )
        raw_token = await service.request_password_reset(email="a@example.com", now_ms=1_000_000_000.0)

        result = await routes.confirm_password_reset(
            routes.PasswordResetConfirmBody(token=raw_token, newPassword="NewStr0ngPass!"), service=service,
        )
        assert "message" in result

        login = await routes.login(
            routes.LoginRequest(emailOrUsername="a@example.com", password="NewStr0ngPass!"),
            client_ip=None, service=service,
        )
        assert login["access_token"]


class TestEmailVerificationEndpoints:
    async def test_verify_email_with_a_valid_token_succeeds(self):
        service = make_service()
        registered = await routes.register(
            routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A"),
            client_ip=None, service=service,
        )
        raw_token = await service.request_email_verification(user_id=registered["id"], now_ms=1_000_000_000.0)

        result = await routes.verify_email(routes.VerifyEmailBody(token=raw_token), service=service)
        assert "message" in result

    async def test_verify_email_with_a_bad_token_raises_400(self):
        service = make_service()
        with pytest.raises(AuthHTTPError) as exc_info:
            await routes.verify_email(routes.VerifyEmailBody(token="garbage"), service=service)
        assert exc_info.value.status_code == 400

    async def test_resend_verification_for_an_unverified_user_succeeds(self):
        service = make_service()
        user = {"id": "u1", "emailVerified": False}
        result = await routes.resend_verification(user=user, service=service)
        assert "message" in result

    async def test_resend_verification_for_an_already_verified_user_raises_400(self):
        service = make_service()
        user = {"id": "u1", "emailVerified": True}
        with pytest.raises(AuthHTTPError) as exc_info:
            await routes.resend_verification(user=user, service=service)
        assert exc_info.value.status_code == 400


class TestAppWiring:
    """A small number of true end-to-end HTTP tests (unlike the rest of this
    file) to prove the router is actually mounted correctly, the exception
    handler produces the right envelope, and Authorization headers are
    parsed by the real ASGI stack."""

    def _make_app(self, service):
        app = FastAPI()
        app.add_exception_handler(AuthHTTPError, auth_http_error_handler)
        app.include_router(routes.router)
        dependencies.set_auth_service(service)
        return app

    def test_register_then_login_over_http(self):
        service = make_service()
        client = TestClient(self._make_app(service))

        register_resp = client.post(
            "/api/auth/register",
            json={"email": "http@example.com", "password": "Str0ngPass!", "displayName": "HTTP"},
        )
        assert register_resp.status_code == 201

        login_resp = client.post(
            "/api/auth/login", json={"emailOrUsername": "http@example.com", "password": "Str0ngPass!"},
        )
        assert login_resp.status_code == 200
        access_token = login_resp.json()["access_token"]

        me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "http@example.com"

    def test_me_without_a_token_returns_the_standard_error_envelope(self):
        service = make_service()
        client = TestClient(self._make_app(service))
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.json() == {"error": "TOKEN_MISSING", "message": "An access token is required.", "details": {}}

    def test_validation_error_on_bad_email_returns_422_from_pydantic(self):
        service = make_service()
        client = TestClient(self._make_app(service))
        resp = client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "Str0ngPass!", "displayName": "X"},
        )
        assert resp.status_code == 422
