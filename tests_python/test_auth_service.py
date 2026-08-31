"""Unit tests for server/auth/service.py: the AuthService business-logic
layer (design doc §7.1, §10). Uses a hand-rolled in-memory FakeUserRepo test
double (same spirit as the FakePool test doubles used elsewhere in
tests_python/) so these tests never touch real SQL or a real clock."""

import pytest

from server.auth.config import AuthConfig, PasswordPolicy, SessionConfig
from server.auth.passwords import hash_password, verify_password
from server.auth.service import (
    AccountLockedError,
    AuthService,
    DuplicateEmailError,
    DuplicateUsernameError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidResetTokenError,
    OAuth2GroupNotAllowedError,
    OAuth2ProfileMissingEmailError,
    RateLimitedError,
    RegistrationDisabledError,
    SessionRevokedError,
    WeakPasswordError,
)
from server.auth.tokens import decode_token
from server.game.rate_limiter import SlidingWindowRateLimiter

SECRET = "test-secret-key-at-least-32-characters-long"
NOW_MS = 1_000_000_000.0


def make_config(**overrides) -> AuthConfig:
    defaults = dict(
        jwt_secret_key=SECRET,
        enable_local_registration=True,
        admin_only_registration=False,
        password_policy=PasswordPolicy(min_length=8),
        session_config=SessionConfig(
            access_token_expire_minutes=30, refresh_token_expire_days=7, max_sessions_per_user=5,
        ),
        registration_rate_limit_per_hour=10,
        login_rate_limit_per_hour=100,
        failed_login_lockout_threshold=5,
        failed_login_lockout_minutes=15,
    )
    defaults.update(overrides)
    return AuthConfig(**defaults)


class FakeUserRepo:
    """In-memory stand-in for the Database auth methods, matching their
    exact async signatures so AuthService can't tell the difference."""

    def __init__(self):
        self.users: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.verification_tokens: dict[str, dict] = {}
        self.reset_tokens: dict[str, dict] = {}
        self.audit_events: list[dict] = []
        self.oauth2_identities: dict[tuple, str] = {}
        self.password_history: dict[str, list[str]] = {}
        self._next_id = 1

    def _new_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    async def create_user(
        self, *, user_id, email, password_hash, display_name, username=None, role="learner",
        created_by=None, email_verified=False, requires_password_change=False,
    ):
        email = email.strip().lower()
        for user in self.users.values():
            if user["email"] == email:
                raise DuplicateEmailError(email)
            if username and user.get("username") == username:
                raise DuplicateUsernameError(username)
        record = {
            "id": user_id, "email": email, "username": username, "displayName": display_name,
            "role": role, "isActive": True, "isAdmin": False, "isModerator": False,
            "emailVerified": email_verified, "requiresPasswordChange": requires_password_change,
            "bio": None, "preferredTopics": None, "failedLoginAttempts": 0, "lockedUntil": None,
            "lastLoginAt": None, "createdAt": NOW_MS, "passwordChangedAt": NOW_MS,
            "_passwordHash": password_hash,
        }
        self.users[user_id] = record
        return {k: v for k, v in record.items() if not k.startswith("_")}

    async def get_user_by_id(self, user_id):
        record = self.users.get(user_id)
        if record is None or record.get("_deleted"):
            return None
        return {k: v for k, v in record.items() if not k.startswith("_")}

    async def get_user_by_email(self, email):
        for record in self.users.values():
            if record["email"] == email.strip().lower():
                return {k: v for k, v in record.items() if not k.startswith("_")}
        return None

    async def get_user_by_username(self, username):
        for record in self.users.values():
            if record.get("username") == username:
                return {k: v for k, v in record.items() if not k.startswith("_")}
        return None

    async def get_user_password_hash(self, user_id):
        record = self.users.get(user_id)
        return record["_passwordHash"] if record else None

    async def update_user(self, user_id, **fields):
        record = self.users.get(user_id)
        if not record:
            return None
        # The real Database.update_user() takes snake_case SQL column names
        # but returns camelCase keys (via _user_row_to_dict); mirror that
        # translation here so this fake behaves the same way.
        translation = {
            "display_name": "displayName", "bio": "bio", "preferred_topics": "preferredTopics",
            "role": "role", "is_active": "isActive", "is_admin": "isAdmin",
            "is_moderator": "isModerator", "email_verified": "emailVerified",
            "requires_password_change": "requiresPasswordChange",
        }
        for key, value in fields.items():
            record[translation.get(key, key)] = value
        return {k: v for k, v in record.items() if not k.startswith("_")}

    async def set_password(self, user_id, password_hash, now_ms=None):
        self.users[user_id]["_passwordHash"] = password_hash
        self.users[user_id]["requiresPasswordChange"] = False
        if now_ms is not None:
            self.users[user_id]["passwordChangedAt"] = now_ms

    async def record_password_history(self, user_id, password_hash, keep_last=5):
        history = self.password_history.setdefault(user_id, [])
        history.insert(0, password_hash)
        del history[keep_last:]

    async def get_password_history(self, user_id, limit=5):
        return self.password_history.get(user_id, [])[:limit]

    async def record_login_success(self, user_id):
        self.users[user_id]["failedLoginAttempts"] = 0
        self.users[user_id]["lockedUntil"] = None

    async def record_login_failure(self, user_id):
        self.users[user_id]["failedLoginAttempts"] += 1
        return self.users[user_id]["failedLoginAttempts"]

    async def lock_account(self, user_id, locked_until):
        self.users[user_id]["lockedUntil"] = locked_until

    async def unlock_account(self, user_id):
        self.users[user_id]["lockedUntil"] = None
        self.users[user_id]["failedLoginAttempts"] = 0

    async def create_session(
        self, *, session_id, user_id, access_token_hash, refresh_token_hash,
        access_expires_at, refresh_expires_at=None, device_name=None, user_agent=None, ip_address=None,
    ):
        record = {
            "id": session_id, "user_id": user_id, "access_token_hash": access_token_hash,
            "refresh_token_hash": refresh_token_hash, "is_active": True,
            "device_name": device_name, "user_agent": user_agent, "ip_address": ip_address,
            "created_at": NOW_MS, "last_activity_at": NOW_MS,
        }
        self.sessions[session_id] = record
        return record

    async def get_session_by_id(self, session_id):
        return self.sessions.get(session_id)

    async def get_session_by_refresh_hash(self, refresh_token_hash):
        for session in self.sessions.values():
            if session["refresh_token_hash"] == refresh_token_hash and session["is_active"]:
                return session
        return None

    async def list_sessions_for_user(self, user_id):
        return sorted(
            (s for s in self.sessions.values() if s["user_id"] == user_id and s["is_active"]),
            key=lambda s: s["created_at"],
        )

    async def revoke_session(self, session_id):
        session = self.sessions.get(session_id)
        if not session or not session["is_active"]:
            return False
        session["is_active"] = False
        return True

    async def revoke_all_sessions_for_user(self, user_id):
        count = 0
        for session in self.sessions.values():
            if session["user_id"] == user_id and session["is_active"]:
                session["is_active"] = False
                count += 1
        return count

    async def touch_session(self, session_id):
        if session_id in self.sessions:
            self.sessions[session_id]["last_activity_at"] = NOW_MS

    async def create_email_verification_token(self, *, token_id, user_id, token_hash, expires_at):
        self.verification_tokens[token_hash] = {"user_id": user_id, "expires_at": expires_at, "used": False}

    async def consume_email_verification_token(self, token_hash):
        record = self.verification_tokens.get(token_hash)
        if not record or record["used"] or record["expires_at"] < NOW_MS:
            return None
        record["used"] = True
        return record["user_id"]

    async def create_password_reset_token(self, *, token_id, user_id, token_hash, expires_at):
        self.reset_tokens[token_hash] = {"user_id": user_id, "expires_at": expires_at, "used": False}

    async def consume_password_reset_token(self, token_hash):
        record = self.reset_tokens.get(token_hash)
        if not record or record["used"] or record["expires_at"] < NOW_MS:
            return None
        record["used"] = True
        return record["user_id"]

    async def log_audit_event(self, **kwargs):
        self.audit_events.append(kwargs)

    async def list_audit_events(self, *, user_id=None, event_type=None, limit=50):
        events = self.audit_events
        if user_id is not None:
            events = [e for e in events if e.get("user_id") == user_id]
        if event_type is not None:
            events = [e for e in events if e.get("event_type") == event_type]
        return list(reversed(events))[:limit]

    async def create_oauth2_identity(self, *, identity_id, user_id, provider, provider_user_id, profile_data=None):
        self.oauth2_identities[(provider, provider_user_id)] = user_id

    async def get_user_id_by_oauth2_identity(self, *, provider, provider_user_id):
        return self.oauth2_identities.get((provider, provider_user_id))

    async def soft_delete_user(self, user_id):
        record = self.users.get(user_id)
        if record is None or record.get("_deleted"):
            return False
        record["_deleted"] = True
        record["isActive"] = False
        return True

    async def list_users(self, *, role=None, is_active=None, limit=50, offset=0):
        records = [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in self.users.values() if not r.get("_deleted")
        ]
        if role is not None:
            records = [r for r in records if r["role"] == role]
        if is_active is not None:
            records = [r for r in records if r["isActive"] == is_active]
        total = len(records)
        return records[offset: offset + limit], total

    async def count_users(self):
        return len([r for r in self.users.values() if not r.get("_deleted")])


def make_service(repo=None, config=None, **rate_limits):
    repo = repo or FakeUserRepo()
    config = config or make_config()
    registration_limiter = SlidingWindowRateLimiter(max_requests=rate_limits.get("reg", 10), window_ms=3_600_000)
    login_limiter = SlidingWindowRateLimiter(max_requests=rate_limits.get("login", 100), window_ms=3_600_000)
    return AuthService(
        repo=repo, config=config,
        registration_rate_limiter=registration_limiter, login_rate_limiter=login_limiter,
    ), repo


class TestRegister:
    async def test_registers_a_new_user_with_a_hashed_password(self):
        service, repo = make_service()
        result = await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice",
            now_ms=NOW_MS, ip="127.0.0.1",
        )
        assert result["email"] == "alice@example.com"
        stored_hash = await repo.get_user_password_hash(result["id"])
        assert stored_hash != "Str0ngPass!"

    async def test_rejects_weak_password(self):
        service, _ = make_service()
        with pytest.raises(WeakPasswordError):
            await service.register(
                email="bob@example.com", password="weak", display_name="Bob", now_ms=NOW_MS,
            )

    async def test_rejects_duplicate_email(self):
        service, _ = make_service()
        await service.register(email="a@example.com", password="Str0ngPass!", display_name="A", now_ms=NOW_MS)
        with pytest.raises(DuplicateEmailError):
            await service.register(email="a@example.com", password="Str0ngPass!2", display_name="A2", now_ms=NOW_MS)

    async def test_rejects_registration_when_disabled(self):
        service, _ = make_service(config=make_config(enable_local_registration=False))
        with pytest.raises(RegistrationDisabledError):
            await service.register(email="a@example.com", password="Str0ngPass!", display_name="A", now_ms=NOW_MS)

    async def test_registration_is_rate_limited_per_ip(self):
        service, _ = make_service(reg=1)
        await service.register(email="a@example.com", password="Str0ngPass!", display_name="A", now_ms=NOW_MS, ip="1.2.3.4")
        with pytest.raises(Exception):
            await service.register(email="b@example.com", password="Str0ngPass!", display_name="B", now_ms=NOW_MS, ip="1.2.3.4")

    async def test_admin_only_mode_forces_requires_password_change_but_is_not_reachable_from_register(self):
        service, _ = make_service(config=make_config(enable_local_registration=False, admin_only_registration=True))
        with pytest.raises(RegistrationDisabledError):
            await service.register(email="a@example.com", password="Str0ngPass!", display_name="A", now_ms=NOW_MS)


class TestLogin:
    async def _register(self, service, email="alice@example.com", password="Str0ngPass!"):
        return await service.register(email=email, password=password, display_name="Alice", now_ms=NOW_MS)

    async def test_successful_login_returns_tokens_and_user(self):
        service, _ = make_service()
        await self._register(service)
        result = await service.login(
            email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS, ip="127.0.0.1",
        )
        assert result["access_token"]
        assert result["refresh_token"]
        assert result["user"]["email"] == "alice@example.com"
        claims = decode_token(result["access_token"], secret=SECRET, expected_type="access")
        assert claims["email"] == "alice@example.com"

    async def test_wrong_password_raises_invalid_credentials(self):
        service, _ = make_service()
        await self._register(service)
        with pytest.raises(InvalidCredentialsError):
            await service.login(email_or_username="alice@example.com", password="WrongPass!", now_ms=NOW_MS)

    async def test_unknown_user_raises_invalid_credentials_not_a_distinct_error(self):
        """Must not leak whether the account exists (user enumeration)."""
        service, _ = make_service()
        with pytest.raises(InvalidCredentialsError):
            await service.login(email_or_username="nobody@example.com", password="whatever", now_ms=NOW_MS)

    async def test_can_login_with_username_as_well_as_email(self):
        repo = FakeUserRepo()
        service, _ = make_service(repo=repo)
        await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice",
            username="alice", now_ms=NOW_MS,
        )
        result = await service.login(email_or_username="alice", password="Str0ngPass!", now_ms=NOW_MS)
        assert result["user"]["username"] == "alice"

    async def test_account_locks_after_reaching_the_failure_threshold(self):
        service, _ = make_service(config=make_config(failed_login_lockout_threshold=3, failed_login_lockout_minutes=15))
        await self._register(service)
        for _ in range(3):
            with pytest.raises(InvalidCredentialsError):
                await service.login(email_or_username="alice@example.com", password="wrong", now_ms=NOW_MS)

        with pytest.raises(AccountLockedError):
            await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)

    async def test_account_unlocks_automatically_after_the_lockout_window_passes(self):
        service, _ = make_service(config=make_config(failed_login_lockout_threshold=1, failed_login_lockout_minutes=15))
        await self._register(service)
        with pytest.raises(InvalidCredentialsError):
            await service.login(email_or_username="alice@example.com", password="wrong", now_ms=NOW_MS)

        later = NOW_MS + (16 * 60 * 1000)
        result = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=later)
        assert result["access_token"]

    async def test_successful_login_resets_the_failure_counter(self):
        service, repo = make_service(config=make_config(failed_login_lockout_threshold=3))
        registered = await self._register(service)
        with pytest.raises(InvalidCredentialsError):
            await service.login(email_or_username="alice@example.com", password="wrong", now_ms=NOW_MS)
        await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)
        user = await repo.get_user_by_id(registered["id"])
        assert user["failedLoginAttempts"] == 0

    async def test_login_is_rate_limited_per_ip(self):
        service, _ = make_service(login=1)
        await self._register(service)
        await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS, ip="9.9.9.9")
        with pytest.raises(Exception):
            await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS, ip="9.9.9.9")

    async def test_disabled_account_cannot_log_in(self):
        service, repo = make_service()
        registered = await self._register(service)
        await repo.update_user(registered["id"], is_active=False)
        with pytest.raises(InvalidCredentialsError):
            await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)

    async def test_unverified_email_cannot_log_in_when_verification_is_required(self):
        service, _ = make_service(config=make_config(require_email_verification=True))
        await self._register(service)
        with pytest.raises(EmailNotVerifiedError):
            await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)

    async def test_verified_email_can_log_in_when_verification_is_required(self):
        service, _ = make_service(config=make_config(require_email_verification=True))
        registered = await self._register(service)
        raw_token = await service.request_email_verification(user_id=registered["id"], now_ms=NOW_MS)
        await service.confirm_email_verification(token=raw_token)
        result = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)
        assert result["access_token"]

    async def test_unverified_email_can_log_in_when_verification_is_not_required(self):
        service, _ = make_service(config=make_config(require_email_verification=False))
        await self._register(service)
        result = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)
        assert result["access_token"]

    async def test_oldest_session_is_revoked_when_session_limit_exceeded(self):
        service, repo = make_service(config=make_config(session_config=SessionConfig(max_sessions_per_user=2)))
        await self._register(service)
        first = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)
        await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS + 1)
        await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS + 2)

        sessions = await repo.list_sessions_for_user(first["user"]["id"])
        assert len(sessions) == 2

    async def test_login_flags_requires_password_change_once_the_password_has_expired(self):
        service, repo = make_service(
            config=make_config(password_policy=PasswordPolicy(min_length=8, expiry_days=90)),
        )
        await self._register(service)
        ninety_one_days_later = NOW_MS + 91 * 86_400_000
        result = await service.login(
            email_or_username="alice@example.com", password="Str0ngPass!", now_ms=ninety_one_days_later,
        )
        assert result["user"]["requiresPasswordChange"] is True
        # Persisted, so a subsequent /api/auth/me (or any other fetch) also sees it.
        stored = await repo.get_user_by_id(result["user"]["id"])
        assert stored["requiresPasswordChange"] is True

    async def test_login_does_not_flag_a_recently_set_password_as_expired(self):
        service, _ = make_service(
            config=make_config(password_policy=PasswordPolicy(min_length=8, expiry_days=90)),
        )
        await self._register(service)
        result = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS + 1)
        assert result["user"]["requiresPasswordChange"] is False

    async def test_expiry_check_is_disabled_when_expiry_days_is_none(self):
        service, _ = make_service(config=make_config(password_policy=PasswordPolicy(min_length=8, expiry_days=None)))
        await self._register(service)
        far_future = NOW_MS + 10_000 * 86_400_000
        result = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=far_future)
        assert result["user"]["requiresPasswordChange"] is False


class TestOAuth2Login:
    def _identity(self, **overrides):
        defaults = dict(provider_user_id="azure-sub-1", email="alice@example.com", name="Alice", picture=None)
        defaults.update(overrides)
        return defaults

    async def test_provisions_a_new_user_on_first_login(self):
        service, repo = make_service()
        result = await service.oauth2_login(provider_name="azure", identity=self._identity(), now_ms=NOW_MS)
        assert result["access_token"]
        assert result["is_new_user"] is True
        assert result["user"]["email"] == "alice@example.com"
        assert result["user"]["emailVerified"] is True
        linked = await repo.get_user_id_by_oauth2_identity(provider="azure", provider_user_id="azure-sub-1")
        assert linked == result["user"]["id"]

    async def test_second_login_reuses_the_linked_account_without_provisioning_again(self):
        service, repo = make_service()
        first = await service.oauth2_login(provider_name="azure", identity=self._identity(), now_ms=NOW_MS)
        second = await service.oauth2_login(provider_name="azure", identity=self._identity(), now_ms=NOW_MS + 1)
        assert second["is_new_user"] is False
        assert second["user"]["id"] == first["user"]["id"]

    async def test_links_to_an_existing_local_account_with_a_matching_email(self):
        service, repo = make_service()
        registered = await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        result = await service.oauth2_login(provider_name="google", identity=self._identity(), now_ms=NOW_MS)
        assert result["is_new_user"] is False
        assert result["user"]["id"] == registered["id"]

    async def test_different_providers_do_not_collide_on_provider_user_id(self):
        service, _ = make_service()
        azure_result = await service.oauth2_login(
            provider_name="azure", identity=self._identity(provider_user_id="same-id", email="a@example.com"),
            now_ms=NOW_MS,
        )
        github_result = await service.oauth2_login(
            provider_name="github", identity=self._identity(provider_user_id="same-id", email="b@example.com"),
            now_ms=NOW_MS,
        )
        assert azure_result["user"]["id"] != github_result["user"]["id"]

    async def test_raises_when_the_provider_gives_no_email_and_no_account_is_linked_yet(self):
        service, _ = make_service()
        with pytest.raises(OAuth2ProfileMissingEmailError):
            await service.oauth2_login(provider_name="github", identity=self._identity(email=None), now_ms=NOW_MS)

    async def test_refuses_to_link_or_provision_on_an_explicitly_unverified_email(self):
        service, repo = make_service()
        await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        with pytest.raises(OAuth2ProfileMissingEmailError):
            await service.oauth2_login(
                provider_name="github", identity=self._identity(email_verified=False), now_ms=NOW_MS,
            )
        # The existing local account must not have been touched.
        linked = await repo.get_user_id_by_oauth2_identity(provider="github", provider_user_id="azure-sub-1")
        assert linked is None

    async def test_disabled_linked_account_cannot_log_in(self):
        service, repo = make_service()
        first = await service.oauth2_login(provider_name="azure", identity=self._identity(), now_ms=NOW_MS)
        await repo.update_user(first["user"]["id"], is_active=False)
        with pytest.raises(SessionRevokedError):
            await service.oauth2_login(provider_name="azure", identity=self._identity(), now_ms=NOW_MS + 1)

    async def test_logs_an_audit_event_naming_the_provider(self):
        service, repo = make_service()
        await service.oauth2_login(provider_name="azure", identity=self._identity(), now_ms=NOW_MS)
        assert any(e["event_type"] == "oauth2_login" and e["event_message"] == "azure" for e in repo.audit_events)

    async def test_oauth2_login_is_rate_limited_per_ip(self):
        service, _ = make_service(login=1)
        await service.oauth2_login(provider_name="azure", identity=self._identity(), now_ms=NOW_MS, ip="9.9.9.9")
        with pytest.raises(RateLimitedError):
            await service.oauth2_login(
                provider_name="azure", identity=self._identity(), now_ms=NOW_MS, ip="9.9.9.9",
            )

    async def test_rejects_login_when_no_allowed_group_matches(self):
        service, _ = make_service()
        with pytest.raises(OAuth2GroupNotAllowedError):
            await service.oauth2_login(
                provider_name="azure", identity=self._identity(groups=["group-x"]), now_ms=NOW_MS,
                allowed_groups=["group-a", "group-b"],
            )

    async def test_allows_login_when_a_group_matches(self):
        service, _ = make_service()
        result = await service.oauth2_login(
            provider_name="azure", identity=self._identity(groups=["group-b"]), now_ms=NOW_MS,
            allowed_groups=["group-a", "group-b"],
        )
        assert result["access_token"]

    async def test_rejects_login_when_identity_has_no_groups_claim_at_all(self):
        service, _ = make_service()
        with pytest.raises(OAuth2GroupNotAllowedError):
            await service.oauth2_login(
                provider_name="azure", identity=self._identity(), now_ms=NOW_MS,
                allowed_groups=["group-a"],
            )

    async def test_no_group_restriction_when_allowed_groups_is_empty(self):
        service, _ = make_service()
        result = await service.oauth2_login(
            provider_name="azure", identity=self._identity(), now_ms=NOW_MS, allowed_groups=[],
        )
        assert result["access_token"]

    async def test_group_check_applies_to_returning_users_too(self):
        service, _ = make_service()
        await service.oauth2_login(provider_name="azure", identity=self._identity(groups=["group-a"]), now_ms=NOW_MS)
        with pytest.raises(OAuth2GroupNotAllowedError):
            await service.oauth2_login(
                provider_name="azure", identity=self._identity(groups=["group-a"]), now_ms=NOW_MS + 1,
                allowed_groups=["group-b"],
            )


class TestRefresh:
    async def _login(self, service):
        await service.register(email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS)
        return await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)

    async def test_refresh_issues_a_new_access_token(self):
        service, _ = make_service()
        logged_in = await self._login(service)
        refreshed = await service.refresh(refresh_token=logged_in["refresh_token"], now_ms=NOW_MS + 1000)
        assert refreshed["access_token"] != logged_in["access_token"]

    async def test_refresh_rejects_an_access_token(self):
        service, _ = make_service()
        logged_in = await self._login(service)
        with pytest.raises(Exception):
            await service.refresh(refresh_token=logged_in["access_token"], now_ms=NOW_MS)

    async def test_refresh_rejects_a_revoked_session(self):
        service, _ = make_service()
        logged_in = await self._login(service)
        await service.logout(access_token=logged_in["access_token"], now_ms=NOW_MS)
        with pytest.raises(Exception):
            await service.refresh(refresh_token=logged_in["refresh_token"], now_ms=NOW_MS)


class TestLogoutAndGetCurrentUser:
    async def _login(self, service):
        await service.register(email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS)
        return await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)

    async def test_get_current_user_returns_the_user_for_a_valid_token(self):
        service, _ = make_service()
        logged_in = await self._login(service)
        user = await service.get_current_user(access_token=logged_in["access_token"], now_ms=NOW_MS)
        assert user["email"] == "alice@example.com"

    async def test_get_current_user_rejects_after_logout(self):
        service, _ = make_service()
        logged_in = await self._login(service)
        await service.logout(access_token=logged_in["access_token"], now_ms=NOW_MS)
        with pytest.raises(Exception):
            await service.get_current_user(access_token=logged_in["access_token"], now_ms=NOW_MS)


class TestChangePassword:
    async def _login(self, service):
        await service.register(email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS)
        return await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)

    async def test_changes_the_password_when_current_password_is_correct(self):
        service, repo = make_service()
        logged_in = await self._login(service)
        await service.change_password(
            user_id=logged_in["user"]["id"], current_password="Str0ngPass!", new_password="NewStr0ngPass!",
        )
        new_login = await service.login(email_or_username="alice@example.com", password="NewStr0ngPass!", now_ms=NOW_MS)
        assert new_login["access_token"]

    async def test_rejects_when_current_password_is_wrong(self):
        service, _ = make_service()
        logged_in = await self._login(service)
        with pytest.raises(InvalidCredentialsError):
            await service.change_password(
                user_id=logged_in["user"]["id"], current_password="WrongOne!", new_password="NewStr0ngPass!",
            )

    async def test_rejects_a_weak_new_password(self):
        service, _ = make_service()
        logged_in = await self._login(service)
        with pytest.raises(WeakPasswordError):
            await service.change_password(
                user_id=logged_in["user"]["id"], current_password="Str0ngPass!", new_password="weak",
            )

    async def test_rejects_reusing_the_current_password(self):
        service, _ = make_service()
        logged_in = await self._login(service)
        with pytest.raises(WeakPasswordError):
            await service.change_password(
                user_id=logged_in["user"]["id"], current_password="Str0ngPass!", new_password="Str0ngPass!",
            )

    async def test_rejects_reusing_a_recently_retired_password(self):
        service, _ = make_service()
        logged_in = await self._login(service)
        user_id = logged_in["user"]["id"]
        await service.change_password(user_id=user_id, current_password="Str0ngPass!", new_password="SecondPass1!")
        with pytest.raises(WeakPasswordError):
            await service.change_password(user_id=user_id, current_password="SecondPass1!", new_password="Str0ngPass!")

    async def test_allows_reuse_once_it_ages_out_of_the_configured_history(self):
        service, _ = make_service(config=make_config(password_policy=PasswordPolicy(min_length=8, history_count=1)))
        logged_in = await self._login(service)
        user_id = logged_in["user"]["id"]
        # history_count=1 means only the live password itself is checked --
        # a password retired one change ago is fair game again.
        await service.change_password(user_id=user_id, current_password="Str0ngPass!", new_password="SecondPass1!")
        await service.change_password(user_id=user_id, current_password="SecondPass1!", new_password="Str0ngPass!")

    async def test_history_check_is_disabled_when_history_count_is_zero(self):
        service, _ = make_service(config=make_config(password_policy=PasswordPolicy(min_length=8, history_count=0)))
        logged_in = await self._login(service)
        user_id = logged_in["user"]["id"]
        await service.change_password(user_id=user_id, current_password="Str0ngPass!", new_password="Str0ngPass!")


class TestPasswordResetFlow:
    async def _register(self, service):
        return await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )

    async def test_full_round_trip_resets_the_password(self):
        service, _ = make_service()
        await self._register(service)
        raw_token = await service.request_password_reset(email="alice@example.com", now_ms=NOW_MS)
        assert raw_token is not None

        await service.confirm_password_reset(token=raw_token, new_password="NewStr0ngPass!")

        new_login = await service.login(email_or_username="alice@example.com", password="NewStr0ngPass!", now_ms=NOW_MS)
        assert new_login["access_token"]

    async def test_request_returns_none_for_unknown_email_without_raising(self):
        service, _ = make_service()
        result = await service.request_password_reset(email="nobody@example.com", now_ms=NOW_MS)
        assert result is None

    async def test_confirm_rejects_an_unknown_token(self):
        service, _ = make_service()
        with pytest.raises(InvalidResetTokenError):
            await service.confirm_password_reset(token="not-a-real-token", new_password="NewStr0ngPass!")

    async def test_confirm_rejects_a_weak_new_password_before_consuming_the_token(self):
        service, _ = make_service()
        await self._register(service)
        raw_token = await service.request_password_reset(email="alice@example.com", now_ms=NOW_MS)
        with pytest.raises(WeakPasswordError):
            await service.confirm_password_reset(token=raw_token, new_password="weak")
        # Token must still be usable since the weak-password rejection happened first.
        await service.confirm_password_reset(token=raw_token, new_password="NewStr0ngPass!")

    async def test_token_cannot_be_reused(self):
        service, _ = make_service()
        await self._register(service)
        raw_token = await service.request_password_reset(email="alice@example.com", now_ms=NOW_MS)
        await service.confirm_password_reset(token=raw_token, new_password="NewStr0ngPass!")
        with pytest.raises(InvalidResetTokenError):
            await service.confirm_password_reset(token=raw_token, new_password="AnotherStr0ngPass!")

    async def test_resetting_the_password_revokes_existing_sessions(self):
        service, _ = make_service()
        await self._register(service)
        logged_in = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)
        raw_token = await service.request_password_reset(email="alice@example.com", now_ms=NOW_MS)
        await service.confirm_password_reset(token=raw_token, new_password="NewStr0ngPass!")

        with pytest.raises(SessionRevokedError):
            await service.refresh(refresh_token=logged_in["refresh_token"], now_ms=NOW_MS)

    async def test_completing_a_reset_clears_an_existing_lockout(self):
        service, _ = make_service(config=make_config(failed_login_lockout_threshold=1))
        registered = await self._register(service)
        with pytest.raises(InvalidCredentialsError):
            await service.login(email_or_username="alice@example.com", password="wrong", now_ms=NOW_MS)
        with pytest.raises(AccountLockedError):
            await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)

        raw_token = await service.request_password_reset(email="alice@example.com", now_ms=NOW_MS)
        await service.confirm_password_reset(token=raw_token, new_password="NewStr0ngPass!")

        # Proving ownership via the emailed reset link should immediately
        # unlock the account, not force a wait for the lockout timer too.
        result = await service.login(email_or_username="alice@example.com", password="NewStr0ngPass!", now_ms=NOW_MS)
        assert result["access_token"]

    async def test_reset_rejects_reusing_the_current_password(self):
        service, _ = make_service()
        await self._register(service)
        raw_token = await service.request_password_reset(email="alice@example.com", now_ms=NOW_MS)
        with pytest.raises(WeakPasswordError):
            await service.confirm_password_reset(token=raw_token, new_password="Str0ngPass!")


class TestEmailVerificationFlow:
    async def _register(self, service):
        return await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )

    async def test_full_round_trip_marks_the_email_verified(self):
        service, repo = make_service()
        user = await self._register(service)
        raw_token = await service.request_email_verification(user_id=user["id"], now_ms=NOW_MS)

        await service.confirm_email_verification(token=raw_token)

        assert repo.users[user["id"]]["emailVerified"] is True

    async def test_confirm_rejects_an_unknown_token(self):
        service, _ = make_service()
        with pytest.raises(InvalidResetTokenError):
            await service.confirm_email_verification(token="not-a-real-token")

    async def test_token_cannot_be_reused(self):
        service, repo = make_service()
        user = await self._register(service)
        raw_token = await service.request_email_verification(user_id=user["id"], now_ms=NOW_MS)
        await service.confirm_email_verification(token=raw_token)
        with pytest.raises(InvalidResetTokenError):
            await service.confirm_email_verification(token=raw_token)


class TestEmailDelivery:
    """Confirms the register/password-reset/admin-create-user flows actually
    dispatch an email through the injected EmailSender, using a spy double
    instead of the real SMTP/logging implementations."""

    class SpyEmailSender:
        def __init__(self):
            self.sent = []

        async def send(self, message):
            self.sent.append(message)

    def _make_service_with_spy(self, **config_overrides):
        spy = self.SpyEmailSender()
        config = make_config(**config_overrides)
        service = AuthService(
            repo=FakeUserRepo(), config=config,
            registration_rate_limiter=SlidingWindowRateLimiter(max_requests=10, window_ms=3_600_000),
            login_rate_limiter=SlidingWindowRateLimiter(max_requests=10, window_ms=3_600_000),
            email_sender=spy,
        )
        return service, spy

    async def test_registration_sends_a_verification_email_when_required(self):
        service, spy = self._make_service_with_spy(require_email_verification=True)
        await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        assert len(spy.sent) == 1
        assert spy.sent[0].to == "alice@example.com"
        assert "verify" in spy.sent[0].subject.lower()

    async def test_registration_sends_no_email_when_verification_is_not_required(self):
        service, spy = self._make_service_with_spy(require_email_verification=False)
        await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        assert spy.sent == []

    async def test_password_reset_request_sends_an_email_to_the_account_owner(self):
        service, spy = self._make_service_with_spy()
        await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        await service.request_password_reset(email="alice@example.com", now_ms=NOW_MS)
        assert len(spy.sent) == 1
        assert spy.sent[0].to == "alice@example.com"
        assert "reset" in spy.sent[0].subject.lower()

    async def test_password_reset_request_sends_no_email_for_an_unknown_address(self):
        service, spy = self._make_service_with_spy()
        await service.request_password_reset(email="nobody@example.com", now_ms=NOW_MS)
        assert spy.sent == []

    async def test_admin_create_user_sends_a_welcome_email_with_the_temporary_password(self):
        service, spy = self._make_service_with_spy()
        _, temp_password = await service.admin_create_user(email="new@example.com", display_name="New User")
        assert len(spy.sent) == 1
        assert spy.sent[0].to == "new@example.com"
        assert temp_password in spy.sent[0].text_body

    async def test_account_lockout_sends_an_alert_email_to_the_account_owner(self):
        service, spy = self._make_service_with_spy(failed_login_lockout_threshold=2)
        await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        for _ in range(2):
            with pytest.raises(InvalidCredentialsError):
                await service.login(email_or_username="alice@example.com", password="wrong", now_ms=NOW_MS)

        assert len(spy.sent) == 1
        assert spy.sent[0].to == "alice@example.com"
        assert "locked" in spy.sent[0].subject.lower()

    async def test_login_does_not_send_a_lockout_email_below_the_failure_threshold(self):
        service, spy = self._make_service_with_spy(failed_login_lockout_threshold=3)
        await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        with pytest.raises(InvalidCredentialsError):
            await service.login(email_or_username="alice@example.com", password="wrong", now_ms=NOW_MS)

        assert spy.sent == []


class TestAdminOperations:
    async def test_admin_create_user_returns_a_temporary_password_that_satisfies_the_policy(self):
        service, repo = make_service()
        user, temp_password = await service.admin_create_user(
            email="new@example.com", display_name="New User", created_by="admin-1",
        )
        assert user["requiresPasswordChange"] is True
        stored_hash = await repo.get_user_password_hash(user["id"])
        assert verify_password(temp_password, stored_hash)

    async def test_admin_created_user_can_log_in_with_the_temporary_password(self):
        service, _ = make_service()
        user, temp_password = await service.admin_create_user(email="new@example.com", display_name="New User")
        result = await service.login(email_or_username="new@example.com", password=temp_password, now_ms=NOW_MS)
        assert result["user"]["requiresPasswordChange"] is True

    async def test_bulk_import_creates_every_valid_row(self):
        service, repo = make_service()
        rows = [
            {"email": "a@example.com", "display_name": "A", "role": "learner"},
            {"email": "b@example.com", "display_name": "B", "role": "educator"},
        ]
        result = await service.admin_bulk_import_users(rows=rows, created_by="admin-1")
        assert result == {"imported": 2, "skipped": 0, "errors": []}
        users, total = await service.list_users()
        assert total == 2

    async def test_bulk_import_skips_a_duplicate_email_but_keeps_going(self):
        service, _ = make_service()
        await service.register(
            email="dup@example.com", password="Str0ngPass!", display_name="Existing", now_ms=NOW_MS,
        )
        rows = [
            {"email": "dup@example.com", "display_name": "Duplicate"},
            {"email": "new@example.com", "display_name": "New"},
        ]
        result = await service.admin_bulk_import_users(rows=rows)
        assert result["imported"] == 1
        assert result["skipped"] == 1
        assert result["errors"] == [{"row": 1, "email": "dup@example.com", "reason": "Email already exists"}]

    async def test_bulk_import_rejects_a_row_with_a_missing_email(self):
        service, _ = make_service()
        result = await service.admin_bulk_import_users(rows=[{"display_name": "No Email"}])
        assert result == {"imported": 0, "skipped": 1, "errors": [{"row": 1, "email": "", "reason": "Missing email"}]}

    async def test_bulk_import_rejects_a_row_with_a_missing_display_name(self):
        service, _ = make_service()
        result = await service.admin_bulk_import_users(rows=[{"email": "a@example.com"}])
        assert result["skipped"] == 1
        assert result["errors"][0]["reason"] == "Missing display_name"

    async def test_bulk_import_rejects_an_invalid_role(self):
        service, _ = make_service()
        result = await service.admin_bulk_import_users(
            rows=[{"email": "a@example.com", "display_name": "A", "role": "superuser"}],
        )
        assert result["skipped"] == 1
        assert "Invalid role" in result["errors"][0]["reason"]

    async def test_bulk_import_defaults_role_to_learner_when_omitted(self):
        service, _ = make_service()
        await service.admin_bulk_import_users(rows=[{"email": "a@example.com", "display_name": "A"}])
        user = await service.get_user_by_email("a@example.com")
        assert user["role"] == "learner"

    async def test_admin_reset_password_issues_a_new_temporary_password_and_revokes_sessions(self):
        service, repo = make_service()
        registered = await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        logged_in = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)
        new_password = await service.admin_reset_password(user_id=registered["id"])

        with pytest.raises(Exception):
            await service.get_current_user(access_token=logged_in["access_token"], now_ms=NOW_MS)
        result = await service.login(email_or_username="alice@example.com", password=new_password, now_ms=NOW_MS)
        assert result["user"]["requiresPasswordChange"] is True

    async def test_admin_update_user_patches_only_the_given_fields(self):
        service, repo = make_service()
        registered = await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        updated = await service.admin_update_user(user_id=registered["id"], role="educator")
        assert updated["role"] == "educator"
        assert updated["displayName"] == "Alice"

    async def test_admin_disable_user_prevents_login_and_revokes_sessions(self):
        service, repo = make_service()
        registered = await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        logged_in = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)
        await service.admin_disable_user(user_id=registered["id"])

        with pytest.raises(Exception):
            await service.get_current_user(access_token=logged_in["access_token"], now_ms=NOW_MS)
        with pytest.raises(InvalidCredentialsError):
            await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)

    async def test_admin_enable_user_allows_login_again(self):
        service, repo = make_service()
        registered = await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        await service.admin_disable_user(user_id=registered["id"])
        await service.admin_enable_user(user_id=registered["id"])
        result = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)
        assert result["access_token"]

    async def test_admin_unlock_user_clears_lockout(self):
        service, repo = make_service(config=make_config(failed_login_lockout_threshold=1))
        registered = await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        with pytest.raises(InvalidCredentialsError):
            await service.login(email_or_username="alice@example.com", password="wrong", now_ms=NOW_MS)
        with pytest.raises(AccountLockedError):
            await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)

        await service.admin_unlock_user(user_id=registered["id"])
        result = await service.login(email_or_username="alice@example.com", password="Str0ngPass!", now_ms=NOW_MS)
        assert result["access_token"]

    async def test_admin_delete_user_soft_deletes(self):
        service, repo = make_service()
        registered = await service.register(
            email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS,
        )
        assert await service.admin_delete_user(user_id=registered["id"]) is True
        assert await service.get_user(registered["id"]) is None

    async def test_list_users_delegates_to_the_repo(self):
        service, _ = make_service()
        await service.register(email="alice@example.com", password="Str0ngPass!", display_name="Alice", now_ms=NOW_MS)
        users, total = await service.list_users()
        assert total == 1
        assert users[0]["email"] == "alice@example.com"

