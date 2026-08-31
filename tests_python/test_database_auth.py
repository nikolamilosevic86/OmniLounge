"""Unit tests for the auth-related persistence methods added to
server/db/database.py (design doc §6). Same fake-asyncpg-pool approach as
tests_python/test_database.py: no real Postgres connection required, and
these tests verify SQL parameter wiring / row-to-dict mapping only."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.db.database import Database, DuplicateEmailError, DuplicateUsernameError


class FakeAcquireContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return FakeAcquireContext(self._conn)


@pytest.fixture
def fake_conn():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock()
    conn.fetchval = AsyncMock()
    return conn


@pytest.fixture
def db(fake_conn):
    database = Database()
    database.pool = FakePool(fake_conn)
    return database


USER_ROW = {
    "id": "user-1",
    "email": "alice@example.com",
    "username": "alice",
    "display_name": "Alice",
    "password_hash": "hashed",
    "role": "learner",
    "is_active": True,
    "is_admin": False,
    "is_moderator": False,
    "email_verified": False,
    "requires_password_change": False,
    "bio": None,
    "preferred_topics": None,
    "failed_login_attempts": 0,
    "locked_until": None,
    "last_login_at": None,
    "created_at": "2026-01-01T00:00:00Z",
    "password_changed_at": None,
}


class TestCreateUser:
    async def test_creates_user_when_email_and_username_are_free(self, db, fake_conn):
        fake_conn.fetchrow.side_effect = [None, None, USER_ROW]

        result = await db.create_user(
            user_id="user-1", email="alice@example.com", password_hash="hashed",
            display_name="Alice", username="alice",
        )

        assert result["email"] == "alice@example.com"
        assert fake_conn.fetchrow.await_count == 3

    async def test_raises_duplicate_email_error_when_email_taken(self, db, fake_conn):
        fake_conn.fetchrow.side_effect = [{"id": "other-user"}]

        with pytest.raises(DuplicateEmailError):
            await db.create_user(
                user_id="user-2", email="alice@example.com", password_hash="hashed",
                display_name="Alice 2",
            )

    async def test_raises_duplicate_username_error_when_username_taken(self, db, fake_conn):
        fake_conn.fetchrow.side_effect = [None, {"id": "other-user"}]

        with pytest.raises(DuplicateUsernameError):
            await db.create_user(
                user_id="user-2", email="bob@example.com", password_hash="hashed",
                display_name="Bob", username="alice",
            )

    async def test_oauth2_only_user_can_be_created_without_a_password(self, db, fake_conn):
        fake_conn.fetchrow.side_effect = [None, USER_ROW]

        await db.create_user(
            user_id="user-3", email="oauth@example.com", password_hash=None, display_name="OAuth User",
        )

        insert_args = fake_conn.fetchrow.call_args_list[-1].args
        assert None in insert_args


class TestGetUser:
    async def test_get_user_by_id_returns_none_when_not_found(self, db, fake_conn):
        fake_conn.fetchrow.return_value = None
        assert await db.get_user_by_id("nope") is None

    async def test_get_user_by_id_maps_row(self, db, fake_conn):
        fake_conn.fetchrow.return_value = USER_ROW
        result = await db.get_user_by_id("user-1")
        assert result["id"] == "user-1"
        assert result["displayName"] == "Alice"

    async def test_get_user_by_email_is_case_insensitive_at_the_query_level(self, db, fake_conn):
        fake_conn.fetchrow.return_value = USER_ROW
        await db.get_user_by_email("ALICE@example.com")
        args = fake_conn.fetchrow.call_args.args
        assert args[1] == "alice@example.com"

    async def test_get_user_by_username_returns_none_when_not_found(self, db, fake_conn):
        fake_conn.fetchrow.return_value = None
        assert await db.get_user_by_username("nobody") is None


class TestUpdateUser:
    async def test_updates_only_allowlisted_fields(self, db, fake_conn):
        fake_conn.fetchrow.return_value = USER_ROW
        await db.update_user("user-1", display_name="New Name", role="educator")
        query = fake_conn.fetchrow.call_args.args[0]
        assert "display_name" in query
        assert "role" in query

    async def test_rejects_a_field_not_on_the_allowlist(self, db, fake_conn):
        with pytest.raises(ValueError):
            await db.update_user("user-1", password_hash="sneaky")

    async def test_no_fields_returns_current_user_without_writing(self, db, fake_conn):
        fake_conn.fetchrow.return_value = USER_ROW
        await db.update_user("user-1")
        fake_conn.execute.assert_not_awaited()


class TestLoginAttemptsAndLockout:
    async def test_record_login_failure_returns_new_attempt_count(self, db, fake_conn):
        fake_conn.fetchrow.return_value = {"failed_login_attempts": 3}
        count = await db.record_login_failure("user-1")
        assert count == 3

    async def test_record_login_success_resets_attempts(self, db, fake_conn):
        await db.record_login_success("user-1")
        query = fake_conn.execute.call_args.args[0]
        assert "failed_login_attempts = 0" in query

    async def test_lock_account_sets_locked_until(self, db, fake_conn):
        await db.lock_account("user-1", 1_800_000_000_000.0)
        args = fake_conn.execute.call_args.args
        assert isinstance(args[1], datetime)
        assert args[1].tzinfo is not None

    async def test_unlock_account_clears_lock_and_attempts(self, db, fake_conn):
        await db.unlock_account("user-1")
        query = fake_conn.execute.call_args.args[0]
        assert "locked_until = NULL" in query
        assert "failed_login_attempts = 0" in query


class TestSessions:
    async def test_create_session_inserts_and_returns_row(self, db, fake_conn):
        fake_conn.fetchrow.return_value = {"id": "sess-1", "user_id": "user-1"}
        result = await db.create_session(
            session_id="sess-1", user_id="user-1",
            access_token_hash="a" * 64, refresh_token_hash="b" * 64,
            access_expires_at=1_800_000_000_000.0, refresh_expires_at=1_800_500_000_000.0,
        )
        assert result["id"] == "sess-1"
        # Both expiry columns are TIMESTAMPTZ; asyncpg needs real datetimes,
        # not the epoch-ms floats AuthService works in internally.
        args = fake_conn.fetchrow.call_args.args
        assert isinstance(args[5], datetime)
        assert isinstance(args[6], datetime)

    async def test_create_session_allows_no_refresh_expiry(self, db, fake_conn):
        fake_conn.fetchrow.return_value = {"id": "sess-1", "user_id": "user-1"}
        await db.create_session(
            session_id="sess-1", user_id="user-1",
            access_token_hash="a" * 64, refresh_token_hash=None,
            access_expires_at=1_800_000_000_000.0,
        )
        args = fake_conn.fetchrow.call_args.args
        assert args[6] is None

    async def test_get_session_by_refresh_hash_returns_none_when_absent(self, db, fake_conn):
        fake_conn.fetchrow.return_value = None
        assert await db.get_session_by_refresh_hash("x" * 64) is None

    async def test_revoke_session_returns_true_when_a_row_was_updated(self, db, fake_conn):
        fake_conn.execute.return_value = "UPDATE 1"
        assert await db.revoke_session("sess-1") is True

    async def test_revoke_session_returns_false_when_no_row_matched(self, db, fake_conn):
        fake_conn.execute.return_value = "UPDATE 0"
        assert await db.revoke_session("sess-missing") is False

    async def test_revoke_all_sessions_for_user_returns_count(self, db, fake_conn):
        fake_conn.execute.return_value = "UPDATE 3"
        assert await db.revoke_all_sessions_for_user("user-1") == 3

    async def test_list_sessions_for_user_maps_rows(self, db, fake_conn):
        fake_conn.fetch.return_value = [{"id": "sess-1", "device_name": "Chrome"}]
        result = await db.list_sessions_for_user("user-1")
        assert result[0]["id"] == "sess-1"

    async def test_delete_expired_sessions_converts_cutoff_to_a_datetime(self, db, fake_conn):
        fake_conn.execute.return_value = "DELETE 4"
        deleted = await db.delete_expired_sessions(1_800_000_000_000.0)
        assert deleted == 4
        args = fake_conn.execute.call_args.args
        assert isinstance(args[1], datetime)


class TestVerificationAndResetTokens:
    async def test_create_email_verification_token_executes_insert(self, db, fake_conn):
        await db.create_email_verification_token(
            token_id="tok-1", user_id="user-1", token_hash="h" * 64, expires_at=1_800_000_000_000.0,
        )
        fake_conn.execute.assert_awaited_once()
        args = fake_conn.execute.call_args.args
        assert isinstance(args[4], datetime)

    async def test_create_password_reset_token_converts_expiry_to_a_datetime(self, db, fake_conn):
        await db.create_password_reset_token(
            token_id="tok-1", user_id="user-1", token_hash="h" * 64, expires_at=1_800_000_000_000.0,
        )
        args = fake_conn.execute.call_args.args
        assert isinstance(args[4], datetime)

    async def test_consume_email_verification_token_returns_none_when_not_found(self, db, fake_conn):
        fake_conn.fetchrow.return_value = None
        assert await db.consume_email_verification_token("missing") is None

    async def test_consume_email_verification_token_returns_user_id_on_success(self, db, fake_conn):
        fake_conn.fetchrow.return_value = {"user_id": "user-1"}
        assert await db.consume_email_verification_token("h" * 64) == "user-1"

    async def test_consume_password_reset_token_returns_none_when_expired_or_used(self, db, fake_conn):
        fake_conn.fetchrow.return_value = None
        assert await db.consume_password_reset_token("h" * 64) is None


class TestAuditLog:
    async def test_log_audit_event_executes_insert(self, db, fake_conn):
        await db.log_audit_event(event_type="login", event_status="success", user_id="user-1")
        fake_conn.execute.assert_awaited_once()

    async def test_list_audit_events_maps_rows(self, db, fake_conn):
        fake_conn.fetch.return_value = [{
            "id": 1, "user_id": "user-1", "event_type": "login", "event_status": "success",
            "event_message": None, "ip_address": None, "user_agent": None, "created_at": "2026-01-01T00:00:00Z",
        }]
        result = await db.list_audit_events()
        assert result[0]["eventType"] == "login"


class TestListUsers:
    async def test_list_users_returns_rows_and_total(self, db, fake_conn):
        fake_conn.fetch.return_value = [USER_ROW]
        fake_conn.fetchval.return_value = 1
        users, total = await db.list_users()
        assert total == 1
        assert users[0]["email"] == "alice@example.com"

    async def test_list_users_filters_by_role(self, db, fake_conn):
        fake_conn.fetch.return_value = []
        fake_conn.fetchval.return_value = 0
        await db.list_users(role="admin")
        query = fake_conn.fetch.call_args.args[0]
        assert "role = " in query


class TestSoftDeleteUser:
    async def test_soft_delete_sets_deleted_at(self, db, fake_conn):
        fake_conn.execute.return_value = "UPDATE 1"
        assert await db.soft_delete_user("user-1") is True

    async def test_soft_delete_returns_false_when_user_missing(self, db, fake_conn):
        fake_conn.execute.return_value = "UPDATE 0"
        assert await db.soft_delete_user("missing") is False


class TestCountUsers:
    async def test_count_active_users_returns_scalar(self, db, fake_conn):
        fake_conn.fetchval.return_value = 5
        assert await db.count_users() == 5


class TestOAuth2Identities:
    async def test_create_oauth2_identity_serializes_profile_data_to_json(self, db, fake_conn):
        await db.create_oauth2_identity(
            identity_id="ident-1", user_id="user-1", provider="azure", provider_user_id="sub-1",
            profile_data={"email": "alice@example.com"},
        )
        args = fake_conn.execute.call_args.args
        assert args[1:5] == ("ident-1", "user-1", "azure", "sub-1")
        assert args[5] == '{"email": "alice@example.com"}'

    async def test_create_oauth2_identity_allows_no_profile_data(self, db, fake_conn):
        await db.create_oauth2_identity(
            identity_id="ident-1", user_id="user-1", provider="azure", provider_user_id="sub-1",
        )
        args = fake_conn.execute.call_args.args
        assert args[5] is None

    async def test_get_user_id_by_oauth2_identity_returns_the_linked_user(self, db, fake_conn):
        fake_conn.fetchrow.return_value = {"user_id": "user-1"}
        result = await db.get_user_id_by_oauth2_identity(provider="azure", provider_user_id="sub-1")
        assert result == "user-1"
        args = fake_conn.fetchrow.call_args.args
        assert args[1:] == ("azure", "sub-1")

    async def test_get_user_id_by_oauth2_identity_returns_none_when_unlinked(self, db, fake_conn):
        fake_conn.fetchrow.return_value = None
        result = await db.get_user_id_by_oauth2_identity(provider="azure", provider_user_id="unknown")
        assert result is None


class TestPasswordHistory:
    async def test_record_password_history_inserts_then_prunes(self, db, fake_conn):
        await db.record_password_history("user-1", "hash-abc", keep_last=5)
        assert fake_conn.execute.await_count == 2
        insert_query, *insert_args = fake_conn.execute.await_args_list[0].args
        assert insert_args[1:] == ["user-1", "hash-abc"]
        prune_query, *prune_args = fake_conn.execute.await_args_list[1].args
        assert prune_args == ["user-1", 5]

    async def test_get_password_history_returns_hashes_most_recent_first(self, db, fake_conn):
        fake_conn.fetch.return_value = [{"password_hash": "h2"}, {"password_hash": "h1"}]
        result = await db.get_password_history("user-1", limit=5)
        assert result == ["h2", "h1"]
        args = fake_conn.fetch.call_args.args
        assert args[1:] == ("user-1", 5)

    async def test_get_password_history_returns_empty_list_when_none(self, db, fake_conn):
        fake_conn.fetch.return_value = []
        assert await db.get_password_history("user-1", limit=5) == []
