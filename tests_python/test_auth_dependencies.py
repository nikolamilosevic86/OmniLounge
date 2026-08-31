"""Unit tests for server/auth/dependencies.py: the FastAPI Depends()
helpers that extract/validate the bearer token and enforce role checks.
Dependency functions are plain async functions, so they're called directly
here with already-resolved arguments -- the same "call the handler
directly" convention tests_python/test_main_metrics.py already uses for
FastAPI route functions, which avoids needing a full ASGI test client just
to exercise business logic."""

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from server.auth import dependencies
from server.auth.errors import AuthHTTPError
from server.auth.service import SessionRevokedError


class FakeService:
    def __init__(self, user=None, raise_error=None):
        self._user = user
        self._raise_error = raise_error

    async def get_current_user(self, *, access_token, now_ms):
        if self._raise_error:
            raise self._raise_error
        return self._user


def creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class TestGetCurrentUser:
    async def test_returns_the_user_for_valid_credentials(self):
        service = FakeService(user={"id": "u1", "role": "learner", "isAdmin": False})
        user = await dependencies.get_current_user(credentials=creds("token"), service=service)
        assert user["id"] == "u1"

    async def test_raises_token_missing_when_no_credentials_given(self):
        service = FakeService(user={"id": "u1"})
        with pytest.raises(AuthHTTPError) as exc_info:
            await dependencies.get_current_user(credentials=None, service=service)
        assert exc_info.value.error == "TOKEN_MISSING"
        assert exc_info.value.status_code == 401

    async def test_translates_session_revoked_error_to_token_invalid(self):
        service = FakeService(raise_error=SessionRevokedError("expired"))
        with pytest.raises(AuthHTTPError) as exc_info:
            await dependencies.get_current_user(credentials=creds("token"), service=service)
        assert exc_info.value.error == "TOKEN_INVALID"
        assert exc_info.value.status_code == 401


class TestRequireRole:
    async def test_allows_a_user_with_the_required_role(self):
        guard = dependencies.require_role("admin")
        user = await guard(user={"role": "admin", "isAdmin": True})
        assert user["role"] == "admin"

    async def test_rejects_a_user_without_the_required_role(self):
        guard = dependencies.require_role("admin")
        with pytest.raises(AuthHTTPError) as exc_info:
            await guard(user={"role": "learner", "isAdmin": False})
        assert exc_info.value.error == "FORBIDDEN"
        assert exc_info.value.status_code == 403

    async def test_is_admin_flag_grants_access_even_if_role_string_differs(self):
        guard = dependencies.require_role("admin")
        user = await guard(user={"role": "moderator", "isAdmin": True})
        assert user["isAdmin"] is True

    async def test_accepts_any_of_several_allowed_roles(self):
        guard = dependencies.require_role("educator", "admin")
        user = await guard(user={"role": "educator", "isAdmin": False})
        assert user["role"] == "educator"


class TestServiceSingleton:
    def test_get_auth_service_raises_before_initialization(self):
        dependencies._service = None
        with pytest.raises(RuntimeError):
            dependencies.get_auth_service()

    def test_set_and_get_auth_service_round_trips(self):
        sentinel = object()
        dependencies.set_auth_service(sentinel)
        try:
            assert dependencies.get_auth_service() is sentinel
        finally:
            dependencies._service = None


class TestGetClientIp:
    def test_returns_the_client_host(self):
        class FakeClient:
            host = "203.0.113.5"

        class FakeRequest:
            client = FakeClient()

        assert dependencies.get_client_ip(FakeRequest()) == "203.0.113.5"

    def test_returns_none_when_no_client_info_is_available(self):
        class FakeRequest:
            client = None

        assert dependencies.get_client_ip(FakeRequest()) is None
