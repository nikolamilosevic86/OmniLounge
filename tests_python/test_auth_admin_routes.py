"""Tests for server/auth/admin_routes.py: the /api/admin/* endpoints.
Handlers are called directly (see test_auth_routes.py's module docstring
for why), plus one TestClient integration test proving the require_role
RBAC dependency actually blocks a non-admin caller over real HTTP."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import admin_routes, dependencies, routes
from server.auth.errors import AuthHTTPError, auth_http_error_handler
from tests_python.test_auth_routes import make_service


class TestCreateUserEndpoint:
    async def test_creates_a_user_and_returns_a_temporary_password(self):
        service = make_service()
        body = admin_routes.AdminCreateUserRequest(email="new@example.com", displayName="New User")
        result = await admin_routes.admin_create_user(body, admin={"id": "admin-1"}, service=service)
        assert result["temporary_password"]
        assert result["email"] == "new@example.com"

    async def test_duplicate_email_raises_409(self):
        service = make_service()
        body = admin_routes.AdminCreateUserRequest(email="new@example.com", displayName="New User")
        await admin_routes.admin_create_user(body, admin={"id": "admin-1"}, service=service)
        with pytest.raises(AuthHTTPError) as exc_info:
            await admin_routes.admin_create_user(body, admin={"id": "admin-1"}, service=service)
        assert exc_info.value.status_code == 409


class TestListAndGetUserEndpoints:
    async def test_list_users_returns_total_and_rows(self):
        service = make_service()
        await admin_routes.admin_create_user(
            admin_routes.AdminCreateUserRequest(email="a@example.com", displayName="A"),
            admin={"id": "admin-1"}, service=service,
        )
        result = await admin_routes.list_users(role=None, is_active=None, limit=50, offset=0, service=service)
        assert result["total"] == 1

    async def test_get_user_raises_404_when_missing(self):
        service = make_service()
        with pytest.raises(AuthHTTPError) as exc_info:
            await admin_routes.get_user(user_id="nope", service=service)
        assert exc_info.value.status_code == 404
        assert exc_info.value.error == "NOT_FOUND"


class TestUpdateAndLifecycleEndpoints:
    async def _create(self, service):
        return await admin_routes.admin_create_user(
            admin_routes.AdminCreateUserRequest(email="a@example.com", displayName="A"),
            admin={"id": "admin-1"}, service=service,
        )

    async def test_update_user_patches_role(self):
        service = make_service()
        created = await self._create(service)
        result = await admin_routes.update_user(
            user_id=created["id"], body=admin_routes.AdminUpdateUserRequest(role="educator"), service=service,
        )
        assert result["role"] == "educator"

    async def test_reset_password_returns_a_new_temporary_password(self):
        service = make_service()
        created = await self._create(service)
        result = await admin_routes.reset_password(user_id=created["id"], service=service)
        assert result["temporary_password"]

    async def test_disable_then_enable_user(self):
        service = make_service()
        created = await self._create(service)
        disable_result = await admin_routes.disable_user(user_id=created["id"], service=service)
        assert disable_result["message"]
        enable_result = await admin_routes.enable_user(user_id=created["id"], service=service)
        assert enable_result["message"]

    async def test_unlock_user(self):
        service = make_service()
        created = await self._create(service)
        result = await admin_routes.unlock_user(user_id=created["id"], service=service)
        assert result["message"]

    async def test_delete_user_returns_204_shape(self):
        service = make_service()
        created = await self._create(service)
        await admin_routes.delete_user(user_id=created["id"], service=service)
        with pytest.raises(AuthHTTPError):
            await admin_routes.get_user(user_id=created["id"], service=service)


class TestAuditLogEndpoint:
    async def test_returns_events(self):
        service = make_service()
        await admin_routes.admin_create_user(
            admin_routes.AdminCreateUserRequest(email="a@example.com", displayName="A"),
            admin={"id": "admin-1"}, service=service,
        )
        result = await admin_routes.get_audit_log(user_id=None, event_type=None, limit=50, service=service)
        assert result["events"]


class TestRbacOverHttp:
    def _make_app(self, service):
        app = FastAPI()
        app.add_exception_handler(AuthHTTPError, auth_http_error_handler)
        app.include_router(routes.router)
        app.include_router(admin_routes.router)
        dependencies.set_auth_service(service)
        return app

    def test_non_admin_cannot_reach_admin_endpoints(self):
        service = make_service()
        client = TestClient(self._make_app(service))

        client.post(
            "/api/auth/register",
            json={"email": "learner@example.com", "password": "Str0ngPass!", "displayName": "Learner"},
        )
        login_resp = client.post(
            "/api/auth/login", json={"emailOrUsername": "learner@example.com", "password": "Str0ngPass!"},
        )
        token = login_resp.json()["access_token"]

        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert resp.json()["error"] == "FORBIDDEN"

    def test_admin_can_reach_admin_endpoints(self):
        service = make_service()
        client = TestClient(self._make_app(service))

        client.post(
            "/api/auth/register",
            json={"email": "boss@example.com", "password": "Str0ngPass!", "displayName": "Boss"},
        )
        login_resp = client.post(
            "/api/auth/login", json={"emailOrUsername": "boss@example.com", "password": "Str0ngPass!"},
        )
        token = login_resp.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()

        # Directly flip the repo's is_admin flag (there is no HTTP endpoint
        # for self-promotion, by design) to simulate an already-admin user.
        service._repo.users[me["id"]]["isAdmin"] = True

        resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestBulkImportEndpoint:
    def _make_app(self, service):
        app = FastAPI()
        app.add_exception_handler(AuthHTTPError, auth_http_error_handler)
        app.include_router(routes.router)
        app.include_router(admin_routes.router)
        dependencies.set_auth_service(service)
        return app

    def _admin_headers(self, client, service):
        client.post(
            "/api/auth/register",
            json={"email": "boss@example.com", "password": "Str0ngPass!", "displayName": "Boss"},
        )
        login_resp = client.post(
            "/api/auth/login", json={"emailOrUsername": "boss@example.com", "password": "Str0ngPass!"},
        )
        token = login_resp.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
        service._repo.users[me["id"]]["isAdmin"] = True
        return {"Authorization": f"Bearer {token}"}

    def test_imports_valid_rows_over_http(self):
        service = make_service()
        client = TestClient(self._make_app(service))
        headers = self._admin_headers(client, service)

        csv_bytes = b"email,username,display_name,role\njohn@example.com,john,John Learner,learner\n"
        resp = client.post(
            "/api/admin/users/import", headers=headers,
            files={"file": ("users.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json() == {"imported": 1, "skipped": 0, "errors": []}

    def test_reports_a_duplicate_email_without_failing_the_whole_batch(self):
        service = make_service()
        client = TestClient(self._make_app(service))
        headers = self._admin_headers(client, service)

        csv_bytes = (
            b"email,display_name,role\n"
            b"boss@example.com,Duplicate,learner\n"
            b"new@example.com,New Person,learner\n"
        )
        resp = client.post(
            "/api/admin/users/import", headers=headers,
            files={"file": ("users.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["imported"] == 1
        assert body["skipped"] == 1
        assert body["errors"][0]["email"] == "boss@example.com"

    def test_rejects_a_non_admin_caller(self):
        service = make_service()
        client = TestClient(self._make_app(service))
        client.post(
            "/api/auth/register",
            json={"email": "learner@example.com", "password": "Str0ngPass!", "displayName": "Learner"},
        )
        login_resp = client.post(
            "/api/auth/login", json={"emailOrUsername": "learner@example.com", "password": "Str0ngPass!"},
        )
        token = login_resp.json()["access_token"]

        resp = client.post(
            "/api/admin/users/import", headers={"Authorization": f"Bearer {token}"},
            files={"file": ("users.csv", b"email,display_name\na@example.com,A\n", "text/csv")},
        )
        assert resp.status_code == 403

