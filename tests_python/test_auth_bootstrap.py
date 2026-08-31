"""Unit tests for server/auth/bootstrap.py: initial admin account creation
on a fresh deployment (design doc §18)."""

import pytest

from server.auth.bootstrap import bootstrap_initial_admin, create_admin_user
from server.auth.config import AuthConfig, PasswordPolicy
from server.auth.service import WeakPasswordError
from server.db.database import DuplicateEmailError
from tests_python.test_auth_service import FakeUserRepo

SECRET = "test-secret-key-at-least-32-characters-long"


def make_config() -> AuthConfig:
    return AuthConfig(jwt_secret_key=SECRET, password_policy=PasswordPolicy(min_length=8))


class TestBootstrapInitialAdmin:
    async def test_creates_an_admin_when_env_vars_are_set_and_no_users_exist(self, monkeypatch):
        monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Str0ngAdminPass!")
        monkeypatch.setenv("INITIAL_ADMIN_DISPLAY_NAME", "System Administrator")
        repo = FakeUserRepo()

        user = await bootstrap_initial_admin(repo, make_config())

        assert user is not None
        assert user["role"] == "admin"
        assert user["isAdmin"] is True
        assert user["requiresPasswordChange"] is True

    async def test_does_nothing_when_env_vars_are_absent(self, monkeypatch):
        monkeypatch.delenv("INITIAL_ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)
        repo = FakeUserRepo()

        user = await bootstrap_initial_admin(repo, make_config())

        assert user is None
        assert repo.users == {}

    async def test_does_nothing_when_users_already_exist(self, monkeypatch):
        monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Str0ngAdminPass!")
        repo = FakeUserRepo()
        await repo.create_user(
            user_id="existing", email="someone@example.com", password_hash="x",
            display_name="Someone",
        )

        user = await bootstrap_initial_admin(repo, make_config())

        assert user is None

    async def test_rejects_a_weak_initial_password_without_crashing_the_server(self, monkeypatch):
        monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "weak")
        repo = FakeUserRepo()

        user = await bootstrap_initial_admin(repo, make_config())

        assert user is None
        assert repo.users == {}

    async def test_missing_password_with_email_set_does_nothing(self, monkeypatch):
        monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
        monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)
        repo = FakeUserRepo()

        user = await bootstrap_initial_admin(repo, make_config())

        assert user is None

    async def test_defaults_display_name_when_not_provided(self, monkeypatch):
        monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Str0ngAdminPass!")
        monkeypatch.delenv("INITIAL_ADMIN_DISPLAY_NAME", raising=False)
        repo = FakeUserRepo()

        user = await bootstrap_initial_admin(repo, make_config())

        assert user["displayName"] == "System Administrator"


class TestCreateAdminUser:
    """Backs the §18.2 CLI bootstrap script -- unlike bootstrap_initial_admin,
    raises instead of silently doing nothing, since a CLI has an operator
    to report the error to."""

    async def test_creates_an_admin_with_the_given_password(self):
        repo = FakeUserRepo()
        user = await create_admin_user(
            repo, make_config(), email="admin@example.com", display_name="Boss", password="Str0ngAdminPass!",
        )
        assert user["role"] == "admin"
        assert user["isAdmin"] is True
        assert user["requiresPasswordChange"] is False
        stored_hash = await repo.get_user_password_hash(user["id"])
        from server.auth.passwords import verify_password
        assert verify_password("Str0ngAdminPass!", stored_hash)

    async def test_rejects_a_weak_password(self):
        repo = FakeUserRepo()
        with pytest.raises(WeakPasswordError):
            await create_admin_user(
                repo, make_config(), email="admin@example.com", display_name="Boss", password="weak",
            )
        assert repo.users == {}

    async def test_rejects_a_duplicate_email(self):
        repo = FakeUserRepo()
        await create_admin_user(
            repo, make_config(), email="admin@example.com", display_name="Boss", password="Str0ngAdminPass!",
        )
        with pytest.raises(DuplicateEmailError):
            await create_admin_user(
                repo, make_config(), email="admin@example.com", display_name="Boss 2", password="An0therPass!",
            )

    async def test_creates_an_admin_with_an_optional_username(self):
        repo = FakeUserRepo()
        user = await create_admin_user(
            repo, make_config(), email="admin@example.com", display_name="Boss",
            password="Str0ngAdminPass!", username="theboss",
        )
        assert user["username"] == "theboss"

