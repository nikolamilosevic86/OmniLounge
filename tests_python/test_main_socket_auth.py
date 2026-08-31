"""Unit tests for server.main.authenticate_socket_connection: the optional,
opt-in JWT check on Socket.IO connect (design doc §16). Off by default so
the existing anonymous real-time game is unaffected; only enforced when
AUTH_REQUIRE_SOCKET_AUTH=true (server.auth.config.auth_config.require_socket_auth)."""

import time

import pytest

import server.main as main_module
from server.auth import dependencies
from server.auth.config import AuthConfig, PasswordPolicy, SessionConfig
from server.auth.service import AuthService
from server.game.rate_limiter import SlidingWindowRateLimiter
from tests_python.test_auth_service import FakeUserRepo

SECRET = "test-secret-key-at-least-32-characters-long"


def make_service(require_socket_auth: bool) -> AuthService:
    config = AuthConfig(
        jwt_secret_key=SECRET, enable_local_registration=True,
        password_policy=PasswordPolicy(min_length=8), session_config=SessionConfig(),
        require_socket_auth=require_socket_auth,
    )
    return AuthService(
        repo=FakeUserRepo(), config=config,
        registration_rate_limiter=SlidingWindowRateLimiter(max_requests=10, window_ms=3_600_000),
        login_rate_limiter=SlidingWindowRateLimiter(max_requests=10, window_ms=3_600_000),
    )


class TestSocketAuthDisabled:
    async def test_returns_none_and_never_checks_the_token_when_disabled(self, monkeypatch):
        service = make_service(require_socket_auth=False)
        monkeypatch.setattr(main_module, "auth_config", service._config)
        dependencies.set_auth_service(service)

        result = await main_module.authenticate_socket_connection(None)
        assert result is None


class TestSocketAuthEnabled:
    async def _logged_in_token(self, service):
        await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=time.time() * 1000,
        )
        result = await service.login(
            email_or_username="alice@example.com", password="Str0ngPass!", now_ms=time.time() * 1000,
        )
        return result["access_token"]

    async def test_accepts_a_valid_token(self, monkeypatch):
        service = make_service(require_socket_auth=True)
        monkeypatch.setattr(main_module, "auth_config", service._config)
        dependencies.set_auth_service(service)
        token = await self._logged_in_token(service)

        user = await main_module.authenticate_socket_connection({"token": token})
        assert user["email"] == "alice@example.com"

    async def test_rejects_a_missing_token(self, monkeypatch):
        service = make_service(require_socket_auth=True)
        monkeypatch.setattr(main_module, "auth_config", service._config)
        dependencies.set_auth_service(service)

        with pytest.raises(ConnectionRefusedError):
            await main_module.authenticate_socket_connection(None)

    async def test_rejects_an_empty_auth_dict(self, monkeypatch):
        service = make_service(require_socket_auth=True)
        monkeypatch.setattr(main_module, "auth_config", service._config)
        dependencies.set_auth_service(service)

        with pytest.raises(ConnectionRefusedError):
            await main_module.authenticate_socket_connection({})

    async def test_rejects_a_garbage_token(self, monkeypatch):
        service = make_service(require_socket_auth=True)
        monkeypatch.setattr(main_module, "auth_config", service._config)
        dependencies.set_auth_service(service)

        with pytest.raises(ConnectionRefusedError):
            await main_module.authenticate_socket_connection({"token": "not-a-real-token"})

    async def test_rejects_a_token_for_a_disabled_account(self, monkeypatch):
        service = make_service(require_socket_auth=True)
        monkeypatch.setattr(main_module, "auth_config", service._config)
        dependencies.set_auth_service(service)
        token = await self._logged_in_token(service)
        me = await service.get_current_user(access_token=token, now_ms=time.time() * 1000)
        await service.admin_disable_user(user_id=me["id"])

        with pytest.raises(ConnectionRefusedError):
            await main_module.authenticate_socket_connection({"token": token})
