import json
import uuid
from datetime import datetime, timezone

import asyncpg

from server.config import DATABASE_URL


def _epoch_ms_to_datetime(epoch_ms):
    """AuthService works entirely in epoch-ms floats (see server/auth/service.py's
    module docstring), but every expiry column in this schema is TIMESTAMPTZ so
    that SQL can compare against NOW() directly (e.g. `expires_at > NOW()` in
    consume_password_reset_token). asyncpg requires a real datetime for a
    timestamptz parameter -- handing it a bare float raises a DataError -- so
    every write site converts here; `_to_epoch_ms` in service.py converts back
    on read."""
    if epoch_ms is None:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)


class DuplicateEmailError(Exception):
    """Raised by create_user() when the email is already registered."""


class DuplicateUsernameError(Exception):
    """Raised by create_user() when the username is already taken."""


# Columns update_user() is allowed to write. Kept as an explicit allowlist
# (rather than accepting arbitrary **kwargs straight from a request body)
# so a column name can never be attacker-controlled: every call site in this
# codebase passes named keyword arguments it decided on itself, and any
# name outside this set is rejected before a query is even built.
_ALLOWED_USER_UPDATE_FIELDS = frozenset({
    "display_name", "bio", "preferred_topics", "role", "is_active",
    "is_admin", "is_moderator", "email_verified", "requires_password_change",
})

_USER_ROW_COLUMNS = (
    "id", "email", "username", "display_name", "role", "is_active", "is_admin",
    "is_moderator", "email_verified", "requires_password_change", "bio",
    "preferred_topics", "failed_login_attempts", "locked_until", "last_login_at",
    "created_at", "password_changed_at",
)


class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

    async def disconnect(self) -> None:
        if self.pool:
            await self.pool.close()

    async def save_avatar(self, avatar: dict) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO avatars (username, skin_color, gender, hair, beard, glasses, clothes, accessory)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (username) DO UPDATE SET
                    skin_color = EXCLUDED.skin_color,
                    gender = EXCLUDED.gender,
                    hair = EXCLUDED.hair,
                    beard = EXCLUDED.beard,
                    glasses = EXCLUDED.glasses,
                    clothes = EXCLUDED.clothes,
                    accessory = EXCLUDED.accessory,
                    updated_at = NOW()
                """,
                avatar["username"],
                avatar["skinColor"],
                avatar.get("gender", "neutral"),
                avatar["hair"],
                avatar["beard"],
                avatar["glasses"],
                avatar["clothes"],
                avatar["accessory"],
            )

    async def get_avatar(self, username: str) -> dict | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM avatars WHERE username = $1",
                username,
            )
        if not row:
            return None
        return {
            "username": row["username"],
            "skinColor": row["skin_color"],
            "gender": row["gender"],
            "hair": row["hair"],
            "beard": row["beard"],
            "glasses": row["glasses"],
            "clothes": row["clothes"],
            "accessory": row["accessory"],
        }

    async def save_message(self, message: dict, room_id: str = "lobby") -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (id, room_id, sender_id, sender_name, text, type, recipient_id, timestamp_ms)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (id) DO NOTHING
                """,
                message["id"],
                room_id,
                message["senderId"],
                message["senderName"],
                message["text"],
                message["type"],
                message.get("recipientId"),
                message["timestamp"],
            )

    async def get_recent_messages(self, room_id: str = "lobby", limit: int = 50) -> list[dict]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, sender_id, sender_name, text, type, recipient_id, timestamp_ms
                FROM messages
                WHERE room_id = $1
                ORDER BY timestamp_ms DESC
                LIMIT $2
                """,
                room_id,
                limit,
            )
        return [
            {
                "id": row["id"],
                "senderId": row["sender_id"],
                "senderName": row["sender_name"],
                "text": row["text"],
                "type": row["type"],
                "recipientId": row["recipient_id"],
                "timestamp": row["timestamp_ms"],
            }
            for row in reversed(rows)
        ]

    # ── Auth: users (design doc §6.1) ────────────────────────────────────

    @staticmethod
    def _user_row_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "email": row["email"],
            "username": row["username"],
            "displayName": row["display_name"],
            "role": row["role"],
            "isActive": row["is_active"],
            "isAdmin": row["is_admin"],
            "isModerator": row["is_moderator"],
            "emailVerified": row["email_verified"],
            "requiresPasswordChange": row["requires_password_change"],
            "bio": row["bio"],
            "preferredTopics": row["preferred_topics"],
            "failedLoginAttempts": row["failed_login_attempts"],
            "lockedUntil": row["locked_until"],
            "lastLoginAt": row["last_login_at"],
            "createdAt": row["created_at"],
            "passwordChangedAt": row["password_changed_at"],
        }

    async def create_user(
        self, *, user_id: str, email: str, password_hash: str | None, display_name: str,
        username: str | None = None, role: str = "learner", created_by: str | None = None,
        email_verified: bool = False, requires_password_change: bool = False,
    ) -> dict:
        """Raises DuplicateEmailError/DuplicateUsernameError if already taken.

        Checked with a SELECT before the INSERT rather than relying solely on
        catching the database's unique-constraint violation: it keeps the
        common case simple and gives each error a specific, user-facing type.
        The UNIQUE constraints in the schema remain the actual backstop
        against a same-instant race between two registrations.
        """
        assert self.pool is not None
        normalized_email = email.strip().lower()
        async with self.pool.acquire() as conn:
            existing_email = await conn.fetchrow(
                "SELECT id FROM users WHERE email = $1 AND deleted_at IS NULL", normalized_email,
            )
            if existing_email:
                raise DuplicateEmailError(normalized_email)
            if username:
                existing_username = await conn.fetchrow(
                    "SELECT id FROM users WHERE username = $1 AND deleted_at IS NULL", username,
                )
                if existing_username:
                    raise DuplicateUsernameError(username)
            row = await conn.fetchrow(
                f"""
                INSERT INTO users (
                    id, email, username, display_name, password_hash, role,
                    created_by, email_verified, requires_password_change, password_changed_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                RETURNING {", ".join(_USER_ROW_COLUMNS)}
                """,
                user_id, normalized_email, username, display_name, password_hash, role,
                created_by, email_verified, requires_password_change,
            )
        return self._user_row_to_dict(row)

    async def get_user_by_id(self, user_id: str) -> dict | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {', '.join(_USER_ROW_COLUMNS)} FROM users WHERE id = $1 AND deleted_at IS NULL",
                user_id,
            )
        return self._user_row_to_dict(row) if row else None

    async def get_user_by_email(self, email: str) -> dict | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {', '.join(_USER_ROW_COLUMNS)} FROM users WHERE email = $1 AND deleted_at IS NULL",
                email.strip().lower(),
            )
        return self._user_row_to_dict(row) if row else None

    async def get_user_by_username(self, username: str) -> dict | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {', '.join(_USER_ROW_COLUMNS)} FROM users WHERE username = $1 AND deleted_at IS NULL",
                username,
            )
        return self._user_row_to_dict(row) if row else None

    async def get_user_password_hash(self, user_id: str) -> str | None:
        """Separate from the other getters so the password hash is never
        accidentally included in a payload built from get_user_by_*()."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT password_hash FROM users WHERE id = $1", user_id)
        return row["password_hash"] if row else None

    async def update_user(self, user_id: str, **fields) -> dict | None:
        unknown = set(fields) - _ALLOWED_USER_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"cannot update fields: {sorted(unknown)}")
        if not fields:
            return await self.get_user_by_id(user_id)

        assert self.pool is not None
        set_clauses = []
        values: list = []
        for column, value in fields.items():
            values.append(value)
            set_clauses.append(f"{column} = ${len(values)}")
        values.append(user_id)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE users SET {", ".join(set_clauses)}, updated_at = NOW()
                WHERE id = ${len(values)} AND deleted_at IS NULL
                RETURNING {", ".join(_USER_ROW_COLUMNS)}
                """,
                *values,
            )
        return self._user_row_to_dict(row) if row else None

    async def set_password(self, user_id: str, password_hash: str, now_ms: float) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET password_hash = $1, password_changed_at = $2,
                    requires_password_change = FALSE, updated_at = NOW()
                WHERE id = $3
                """,
                password_hash, _epoch_ms_to_datetime(now_ms), user_id,
            )

    async def record_login_success(self, user_id: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users
                SET failed_login_attempts = 0, locked_until = NULL,
                    last_login_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                user_id,
            )

    async def record_login_failure(self, user_id: str) -> int:
        """Increments and returns the new failed-attempt count so the
        caller can decide whether to lock the account."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE users SET failed_login_attempts = failed_login_attempts + 1, updated_at = NOW()
                WHERE id = $1
                RETURNING failed_login_attempts
                """,
                user_id,
            )
        return row["failed_login_attempts"] if row else 0

    async def lock_account(self, user_id: str, locked_until) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET locked_until = $1, updated_at = NOW() WHERE id = $2",
                _epoch_ms_to_datetime(locked_until), user_id,
            )

    async def unlock_account(self, user_id: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users SET locked_until = NULL, failed_login_attempts = 0, updated_at = NOW()
                WHERE id = $1
                """,
                user_id,
            )

    async def soft_delete_user(self, user_id: str) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET deleted_at = NOW(), is_active = FALSE WHERE id = $1 AND deleted_at IS NULL",
                user_id,
            )
        return result.endswith(" 1")

    async def list_users(
        self, *, role: str | None = None, is_active: bool | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict], int]:
        assert self.pool is not None
        conditions = ["deleted_at IS NULL"]
        params: list = []
        if role is not None:
            params.append(role)
            conditions.append(f"role = ${len(params)}")
        if is_active is not None:
            params.append(is_active)
            conditions.append(f"is_active = ${len(params)}")
        where_clause = " AND ".join(conditions)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {", ".join(_USER_ROW_COLUMNS)} FROM users
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
                """,
                *params, limit, offset,
            )
            total = await conn.fetchval(f"SELECT COUNT(*) FROM users WHERE {where_clause}", *params)
        return [self._user_row_to_dict(row) for row in rows], total

    async def count_users(self) -> int:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL")
        return total

    # ── Auth: sessions (design doc §6.2) ─────────────────────────────────

    async def create_session(
        self, *, session_id: str, user_id: str, access_token_hash: str, refresh_token_hash: str | None,
        access_expires_at, refresh_expires_at=None, device_name: str | None = None,
        user_agent: str | None = None, ip_address: str | None = None,
    ) -> dict:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO user_sessions (
                    id, user_id, access_token_hash, refresh_token_hash,
                    access_token_expires_at, refresh_token_expires_at,
                    device_name, user_agent, ip_address
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id, user_id, device_name, user_agent, ip_address,
                          created_at, last_activity_at
                """,
                session_id, user_id, access_token_hash, refresh_token_hash,
                _epoch_ms_to_datetime(access_expires_at), _epoch_ms_to_datetime(refresh_expires_at),
                device_name, user_agent, ip_address,
            )
        return dict(row)

    async def get_session_by_refresh_hash(self, refresh_token_hash: str) -> dict | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM user_sessions
                WHERE refresh_token_hash = $1 AND is_active = TRUE
                """,
                refresh_token_hash,
            )
        return dict(row) if row else None

    async def get_session_by_id(self, session_id: str) -> dict | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM user_sessions WHERE id = $1", session_id)
        return dict(row) if row else None

    async def list_sessions_for_user(self, user_id: str) -> list[dict]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, device_name, user_agent, ip_address, created_at, last_activity_at
                FROM user_sessions
                WHERE user_id = $1 AND is_active = TRUE
                ORDER BY last_activity_at DESC
                """,
                user_id,
            )
        return [dict(row) for row in rows]

    async def revoke_session(self, session_id: str) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE user_sessions SET is_active = FALSE, revoked_at = NOW() WHERE id = $1 AND is_active = TRUE",
                session_id,
            )
        return result.endswith(" 1")

    async def revoke_all_sessions_for_user(self, user_id: str) -> int:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE user_sessions SET is_active = FALSE, revoked_at = NOW() WHERE user_id = $1 AND is_active = TRUE",
                user_id,
            )
        return int(result.rsplit(" ", 1)[-1])

    async def touch_session(self, session_id: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_sessions SET last_activity_at = NOW() WHERE id = $1", session_id,
            )

    async def delete_expired_sessions(self, now_ms: float) -> int:
        """Housekeeping (design doc Phase 6 T6.4): purges rows whose last
        possible expiry (refresh if present, else access) is in the past,
        regardless of `is_active` -- a session table row is useless once
        neither of its tokens could ever be valid again."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM user_sessions
                WHERE COALESCE(refresh_token_expires_at, access_token_expires_at) < $1
                """,
                _epoch_ms_to_datetime(now_ms),
            )
        return int(result.rsplit(" ", 1)[-1])

    # ── Auth: email verification & password reset tokens (design doc §6.4/§6.5) ──

    async def create_email_verification_token(
        self, *, token_id: str, user_id: str, token_hash: str, expires_at,
    ) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO email_verification_tokens (id, user_id, token_hash, expires_at)
                VALUES ($1, $2, $3, $4)
                """,
                token_id, user_id, token_hash, _epoch_ms_to_datetime(expires_at),
            )

    async def consume_email_verification_token(self, token_hash: str) -> str | None:
        """Atomically marks the token used and returns the owning user id,
        or None if the hash is unknown, already used, or expired. A single
        UPDATE ... RETURNING avoids a check-then-use race between two
        concurrent requests both consuming the same token."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE email_verification_tokens SET used_at = NOW()
                WHERE token_hash = $1 AND used_at IS NULL AND expires_at > NOW()
                RETURNING user_id
                """,
                token_hash,
            )
        return row["user_id"] if row else None

    async def create_password_reset_token(
        self, *, token_id: str, user_id: str, token_hash: str, expires_at,
    ) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at)
                VALUES ($1, $2, $3, $4)
                """,
                token_id, user_id, token_hash, _epoch_ms_to_datetime(expires_at),
            )

    async def consume_password_reset_token(self, token_hash: str) -> str | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE password_reset_tokens SET used_at = NOW()
                WHERE token_hash = $1 AND used_at IS NULL AND expires_at > NOW()
                RETURNING user_id
                """,
                token_hash,
            )
        return row["user_id"] if row else None

    # ── Auth: audit log (design doc §6.6) ────────────────────────────────

    async def log_audit_event(
        self, *, event_type: str, event_status: str, user_id: str | None = None,
        event_message: str | None = None, ip_address: str | None = None, user_agent: str | None = None,
    ) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO auth_audit_log (user_id, event_type, event_status, event_message, ip_address, user_agent)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                user_id, event_type, event_status, event_message, ip_address, user_agent,
            )

    async def list_audit_events(
        self, *, user_id: str | None = None, event_type: str | None = None, limit: int = 50,
    ) -> list[dict]:
        assert self.pool is not None
        conditions = []
        params: list = []
        if user_id is not None:
            params.append(user_id)
            conditions.append(f"user_id = ${len(params)}")
        if event_type is not None:
            params.append(event_type)
            conditions.append(f"event_type = ${len(params)}")
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, user_id, event_type, event_status, event_message, ip_address, user_agent, created_at
                FROM auth_audit_log
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${len(params)}
                """,
                *params,
            )
        return [
            {
                "id": row["id"],
                "userId": row["user_id"],
                "eventType": row["event_type"],
                "eventStatus": row["event_status"],
                "eventMessage": row["event_message"],
                "ipAddress": row["ip_address"],
                "userAgent": row["user_agent"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    # ── Auth: OAuth2 identities (design doc §6.3) ────────────────────────

    async def create_oauth2_identity(
        self, *, identity_id: str, user_id: str, provider: str, provider_user_id: str,
        profile_data: dict | None = None,
    ) -> None:
        """Upserts on (provider, provider_user_id) so re-logging in with the
        same provider account resyncs the cached profile_data instead of
        raising a unique-constraint violation."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO oauth2_identities (id, user_id, provider, provider_user_id, profile_data, last_synced_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (provider, provider_user_id) DO UPDATE SET
                    profile_data = EXCLUDED.profile_data, last_synced_at = NOW()
                """,
                identity_id, user_id, provider, provider_user_id,
                json.dumps(profile_data) if profile_data is not None else None,
            )

    async def get_user_id_by_oauth2_identity(self, *, provider: str, provider_user_id: str) -> str | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id FROM oauth2_identities WHERE provider = $1 AND provider_user_id = $2",
                provider, provider_user_id,
            )
        return row["user_id"] if row else None

    # ── Auth: password history (design doc Phase 7 T7.3) ─────────────────

    async def record_password_history(self, user_id: str, password_hash: str, keep_last: int = 5) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO password_history (id, user_id, password_hash) VALUES ($1, $2, $3)",
                str(uuid.uuid4()), user_id, password_hash,
            )
            await conn.execute(
                """
                DELETE FROM password_history
                WHERE user_id = $1 AND id NOT IN (
                    SELECT id FROM password_history WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2
                )
                """,
                user_id, keep_last,
            )

    async def get_password_history(self, user_id: str, limit: int = 5) -> list[str]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT password_hash FROM password_history WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
                user_id, limit,
            )
        return [row["password_hash"] for row in rows]


