"""Tests for server/auth/user_routes.py: /api/user/* self-service
endpoints (profile, password change, sessions)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import dependencies, routes, user_routes
from server.auth.errors import AuthHTTPError, auth_http_error_handler
from tests_python.test_auth_routes import make_service


class TestProfileEndpoints:
    async def test_get_profile_returns_the_current_user(self):
        service = make_service()
        user = {
            "id": "u1", "email": "a@example.com", "displayName": "A", "role": "learner",
            "bio": None, "preferredTopics": None, "createdAt": "2026-01-01T00:00:00Z",
        }
        result = await user_routes.get_profile(user=user)
        assert result["email"] == "a@example.com"

    async def test_patch_profile_updates_bio(self):
        service = make_service()
        body = routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A")
        registered = await routes.register(body, client_ip=None, service=service)
        result = await user_routes.update_profile(
            body=user_routes.ProfileUpdateRequest(bio="I love learning!"),
            user={"id": registered["id"]}, service=service,
        )
        assert result["bio"] == "I love learning!"


class TestPasswordChangeEndpoint:
    async def _register_and_login(self, service):
        await routes.register(
            routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A"),
            client_ip=None, service=service,
        )
        return await routes.login(
            routes.LoginRequest(emailOrUsername="a@example.com", password="Str0ngPass!"),
            client_ip=None, service=service,
        )

    async def test_changes_password_successfully(self):
        service = make_service()
        logged_in = await self._register_and_login(service)
        result = await user_routes.change_password(
            body=user_routes.PasswordChangeRequest(currentPassword="Str0ngPass!", newPassword="NewStr0ngPass!"),
            user={"id": logged_in["user"]["id"]}, service=service,
        )
        assert result["message"]

    async def test_wrong_current_password_raises_401(self):
        service = make_service()
        logged_in = await self._register_and_login(service)
        with pytest.raises(AuthHTTPError) as exc_info:
            await user_routes.change_password(
                body=user_routes.PasswordChangeRequest(currentPassword="wrong", newPassword="NewStr0ngPass!"),
                user={"id": logged_in["user"]["id"]}, service=service,
            )
        assert exc_info.value.status_code == 401


class TestSessionEndpoints:
    async def _register_and_login(self, service):
        await routes.register(
            routes.RegisterRequest(email="a@example.com", password="Str0ngPass!", displayName="A"),
            client_ip=None, service=service,
        )
        return await routes.login(
            routes.LoginRequest(emailOrUsername="a@example.com", password="Str0ngPass!"),
            client_ip=None, service=service,
        )

    async def test_list_sessions_includes_the_current_session(self):
        service = make_service()
        logged_in = await self._register_and_login(service)
        result = await user_routes.list_sessions(user={"id": logged_in["user"]["id"]}, service=service)
        assert len(result["sessions"]) == 1

    async def test_revoke_session_removes_it_from_the_list(self):
        service = make_service()
        logged_in = await self._register_and_login(service)
        sessions = await user_routes.list_sessions(user={"id": logged_in["user"]["id"]}, service=service)
        session_id = sessions["sessions"][0]["id"]

        result = await user_routes.revoke_session(
            session_id=session_id, user={"id": logged_in["user"]["id"]}, service=service,
        )
        assert result["message"]
        after = await user_routes.list_sessions(user={"id": logged_in["user"]["id"]}, service=service)
        assert len(after["sessions"]) == 0

    async def test_cannot_revoke_another_users_session(self):
        service = make_service()
        logged_in = await self._register_and_login(service)
        sessions = await user_routes.list_sessions(user={"id": logged_in["user"]["id"]}, service=service)
        session_id = sessions["sessions"][0]["id"]

        with pytest.raises(AuthHTTPError) as exc_info:
            await user_routes.revoke_session(session_id=session_id, user={"id": "someone-else"}, service=service)
        assert exc_info.value.status_code == 404


class TestHttpWiring:
    def test_full_profile_and_session_flow_over_http(self):
        service = make_service()
        app = FastAPI()
        app.add_exception_handler(AuthHTTPError, auth_http_error_handler)
        app.include_router(routes.router)
        app.include_router(user_routes.router)
        dependencies.set_auth_service(service)
        client = TestClient(app)

        client.post(
            "/api/auth/register",
            json={"email": "http@example.com", "password": "Str0ngPass!", "displayName": "HTTP"},
        )
        login = client.post(
            "/api/auth/login", json={"emailOrUsername": "http@example.com", "password": "Str0ngPass!"},
        ).json()
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        profile_resp = client.patch("/api/user/profile", json={"bio": "hello"}, headers=headers)
        assert profile_resp.status_code == 200
        assert profile_resp.json()["bio"] == "hello"

        sessions_resp = client.get("/api/user/sessions", headers=headers)
        assert sessions_resp.status_code == 200
        assert len(sessions_resp.json()["sessions"]) == 1
