"""AuthService: the business-logic layer for local authentication (design
doc §7.1, §10). Takes an injected `repo` (any object exposing the same
async methods as server.db.database.Database's auth section) so this class
can be unit tested against a fast in-memory fake and used in production
with the real database, unchanged.
"""

import secrets
import time
import uuid

from server.auth.config import AuthConfig
from server.auth.email import (
    EmailSender,
    LoggingEmailSender,
    build_account_locked_email,
    build_password_reset_email,
    build_verification_email,
    build_welcome_email,
)
from server.auth.passwords import (
    generate_temporary_password,
    hash_password,
    validate_password_strength,
    verify_password,
)
from server.auth.tokens import (
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)
from server.db.database import DuplicateEmailError, DuplicateUsernameError

__all__ = [
    "ALLOWED_ROLES", "AccountLockedError", "AuthService", "BulkImportTooLargeError",
    "DuplicateEmailError", "DuplicateUsernameError", "InvalidCredentialsError", "InvalidResetTokenError",
    "OAuth2GroupNotAllowedError", "OAuth2ProfileMissingEmailError", "RateLimitedError",
    "RegistrationDisabledError", "SessionRevokedError", "WeakPasswordError",
]

# Single source of truth for valid roles -- must match schema.sql's
# chk_users_role CHECK constraint exactly, or a validated request could still
# hit a database constraint violation instead of a clean 400.
ALLOWED_ROLES = ("learner", "educator", "moderator", "admin")

# A CSV bulk-import request is otherwise unbounded synchronous work over an
# admin-only endpoint; capping row count keeps one oversized upload from
# tying up a worker for an unreasonable amount of time.
MAX_BULK_IMPORT_ROWS = 1000


class AuthError(Exception):
    """Base class for all AuthService errors."""


class RegistrationDisabledError(AuthError):
    pass


class WeakPasswordError(AuthError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class InvalidCredentialsError(AuthError):
    pass


class AccountLockedError(AuthError):
    def __init__(self, locked_until_ms: float):
        super().__init__("account is temporarily locked")
        self.locked_until_ms = locked_until_ms


class EmailNotVerifiedError(AuthError):
    pass


class SessionRevokedError(AuthError):
    pass


class RateLimitedError(AuthError):
    pass


class InvalidResetTokenError(AuthError):
    """A password-reset or email-verification link is unknown, already used,
    or expired -- distinct from InvalidCredentialsError because this is
    about a one-time link, not a login attempt."""


class OAuth2ProfileMissingEmailError(AuthError):
    """The identity provider did not return an email address for this user
    (e.g. a GitHub account with no verified public/primary email) -- there
    is nothing to link a local account to or provision a new one with."""


class OAuth2GroupNotAllowedError(AuthError):
    """design doc §4.3: this provider is configured with an allowed_groups
    restriction, and the identity's `groups` claim doesn't overlap it."""


class BulkImportTooLargeError(AuthError):
    pass


# A bcrypt hash of an arbitrary fixed string, used only to burn roughly the
# same amount of CPU time as a real password check when the account being
# "logged into" doesn't actually exist -- otherwise a missing-user login
# returns faster than a wrong-password login, letting an attacker enumerate
# valid emails/usernames purely by timing the response.
_DUMMY_HASH = hash_password("not-a-real-password-just-for-timing-1!")


class AuthService:
    def __init__(
        self, *, repo, config: AuthConfig, registration_rate_limiter, login_rate_limiter,
        email_sender: EmailSender | None = None,
    ) -> None:
        self._repo = repo
        self._config = config
        self._registration_limiter = registration_rate_limiter
        self._login_limiter = login_rate_limiter
        self._email_sender = email_sender or LoggingEmailSender()

    # ── Registration ─────────────────────────────────────────────────────

    async def register(
        self, *, email: str, password: str, display_name: str, now_ms: float,
        username: str | None = None, ip: str | None = None,
    ) -> dict:
        if not self._config.enable_local_registration:
            raise RegistrationDisabledError("open registration is disabled")

        if ip is not None and not self._registration_limiter.allow(ip, now_ms):
            raise RateLimitedError("too many registration attempts, please try again later")

        policy = self._config.password_policy
        strength = validate_password_strength(
            password,
            min_length=policy.min_length,
            require_uppercase=policy.require_uppercase,
            require_lowercase=policy.require_lowercase,
            require_digits=policy.require_digits,
            require_special=policy.require_special,
            username=username,
        )
        if not strength.valid:
            raise WeakPasswordError(strength.errors)

        user = await self._repo.create_user(
            user_id=str(uuid.uuid4()), email=email, password_hash=hash_password(password),
            display_name=display_name, username=username,
            email_verified=not self._config.require_email_verification,
        )
        await self._repo.log_audit_event(
            user_id=user["id"], event_type="registration", event_status="success", ip_address=ip,
        )
        if self._config.require_email_verification:
            await self.request_email_verification(user_id=user["id"], now_ms=now_ms)
        return user

    # ── Login ─────────────────────────────────────────────────────────────

    async def login(
        self, *, email_or_username: str, password: str, now_ms: float,
        ip: str | None = None, user_agent: str | None = None, device_name: str | None = None,
    ) -> dict:
        if ip is not None and not self._login_limiter.allow(ip, now_ms):
            raise RateLimitedError("too many login attempts, please try again later")

        user = await self._find_user(email_or_username)
        if user is None:
            # Burn comparable CPU time to a real check so response timing
            # doesn't reveal whether the account exists.
            verify_password(password, _DUMMY_HASH)
            await self._repo.log_audit_event(
                event_type="login", event_status="failure", ip_address=ip,
                event_message="unknown user",
            )
            raise InvalidCredentialsError("invalid email/username or password")

        locked_until = user.get("lockedUntil")
        if locked_until is not None and _to_epoch_ms(locked_until) > now_ms:
            raise AccountLockedError(_to_epoch_ms(locked_until))

        if not user["isActive"]:
            await self._repo.log_audit_event(
                user_id=user["id"], event_type="login", event_status="failure", ip_address=ip,
                event_message="account disabled",
            )
            raise InvalidCredentialsError("invalid email/username or password")

        stored_hash = await self._repo.get_user_password_hash(user["id"])
        if not stored_hash or not verify_password(password, stored_hash):
            attempts = await self._repo.record_login_failure(user["id"])
            await self._repo.log_audit_event(
                user_id=user["id"], event_type="login", event_status="failure", ip_address=ip,
                event_message="wrong password",
            )
            if attempts >= self._config.failed_login_lockout_threshold:
                locked_until_ms = now_ms + self._config.failed_login_lockout_minutes * 60_000
                await self._repo.lock_account(user["id"], locked_until_ms)
                await self._email_sender.send(
                    build_account_locked_email(
                        to=user["email"], lockout_minutes=self._config.failed_login_lockout_minutes,
                    )
                )
            raise InvalidCredentialsError("invalid email/username or password")

        if self._config.require_email_verification and not user["emailVerified"]:
            await self._repo.log_audit_event(
                user_id=user["id"], event_type="login", event_status="failure", ip_address=ip,
                event_message="email not verified",
            )
            raise EmailNotVerifiedError("please verify your email address before logging in")

        await self._repo.record_login_success(user["id"])
        await self._enforce_expiry_if_configured(user, now_ms=now_ms)
        await self._enforce_session_limit(user["id"])
        session = await self._issue_session(
            user=user, now_ms=now_ms, ip=ip, user_agent=user_agent, device_name=device_name,
        )
        await self._repo.log_audit_event(
            user_id=user["id"], event_type="login", event_status="success", ip_address=ip,
        )
        return session

    async def _find_user(self, email_or_username: str) -> dict | None:
        if "@" in email_or_username:
            return await self._repo.get_user_by_email(email_or_username)
        user = await self._repo.get_user_by_username(email_or_username)
        if user is not None:
            return user
        return await self._repo.get_user_by_email(email_or_username)

    async def _enforce_session_limit(self, user_id: str) -> None:
        max_sessions = self._config.session_config.max_sessions_per_user
        sessions = await self._repo.list_sessions_for_user(user_id)
        if len(sessions) < max_sessions:
            return
        oldest_first = sorted(sessions, key=lambda s: s["created_at"])
        for session in oldest_first[: len(sessions) - max_sessions + 1]:
            await self._repo.revoke_session(session["id"])

    async def _enforce_expiry_if_configured(self, user: dict, *, now_ms: float) -> None:
        """design doc §5.1 PasswordPolicy.expiry_days: doesn't block the
        login itself (matching how `requires_password_change` already works
        for first-login/admin-reset elsewhere) -- just flags the account so
        the frontend redirects to a forced change-password screen, and
        reflects that in the `user` dict this same login response embeds so
        the caller doesn't need a second round-trip to see it."""
        expiry_days = self._config.password_policy.expiry_days
        if not expiry_days:
            return
        changed_at = user.get("passwordChangedAt")
        if changed_at is None:
            return
        age_ms = now_ms - _to_epoch_ms(changed_at)
        if age_ms > expiry_days * 86_400_000:
            await self._repo.update_user(user["id"], requires_password_change=True)
            user["requiresPasswordChange"] = True

    async def _issue_session(
        self, *, user: dict, now_ms: float, ip: str | None, user_agent: str | None, device_name: str | None,
    ) -> dict:
        session_id = str(uuid.uuid4())
        access_expires_in = self._config.session_config.access_token_expire_minutes * 60
        refresh_expires_in = self._config.session_config.refresh_token_expire_days * 86400

        access_token = create_access_token(
            user_id=user["id"], email=user["email"], role=user["role"], session_id=session_id,
            secret=self._config.jwt_secret_key, expires_in_seconds=access_expires_in,
        )
        refresh_token = create_refresh_token(
            user_id=user["id"], session_id=session_id,
            secret=self._config.jwt_secret_key, expires_in_seconds=refresh_expires_in,
        )
        await self._repo.create_session(
            session_id=session_id, user_id=user["id"],
            access_token_hash=hash_token(access_token), refresh_token_hash=hash_token(refresh_token),
            access_expires_at=now_ms + access_expires_in * 1000,
            refresh_expires_at=now_ms + refresh_expires_in * 1000,
            device_name=device_name, user_agent=user_agent, ip_address=ip,
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": access_expires_in,
            "user": user,
        }

    # ── OAuth2 / OIDC login (design doc §4.3, §4.4) ──────────────────────

    async def oauth2_login(
        self, *, provider_name: str, identity: dict, now_ms: float,
        default_role: str = "learner", ip: str | None = None, user_agent: str | None = None,
        allowed_groups: list[str] | None = None,
    ) -> dict:
        """`identity` is the normalized dict returned by
        server.auth.oauth2.resolve_provider_identity(): provider_user_id,
        email, name, picture. Links to an existing oauth2_identities row if
        one exists; otherwise links by matching email, or auto-provisions a
        brand-new account (design doc §4.3/§4.4's 'auto-provision' flow).
        """
        if ip is not None and not self._login_limiter.allow(ip, now_ms):
            raise RateLimitedError("too many login attempts, please try again later")

        # design doc §4.3 "allowed_groups": enforced on every login (not just
        # first), so removing someone from the group takes effect immediately.
        if allowed_groups:
            identity_groups = set(identity.get("groups") or [])
            if identity_groups.isdisjoint(allowed_groups):
                raise OAuth2GroupNotAllowedError(
                    f"this account is not a member of an allowed group for {provider_name}"
                )

        provider_user_id = identity["provider_user_id"]
        is_new_user = False

        linked_user_id = await self._repo.get_user_id_by_oauth2_identity(
            provider=provider_name, provider_user_id=provider_user_id,
        )
        if linked_user_id is not None:
            user = await self._repo.get_user_by_id(linked_user_id)
            if user is None:
                raise SessionRevokedError("linked account no longer exists")
        else:
            email = identity.get("email")
            if not email:
                raise OAuth2ProfileMissingEmailError(f"{provider_name} did not provide an email address")
            # An explicit `email_verified: false` means the provider itself
            # does not vouch for this address -- linking or auto-provisioning
            # on it would let anyone claim a victim's email at a lenient
            # provider and take over (or silently merge into) their account.
            # A missing claim (common for enterprise IdPs) is treated as
            # trusted, matching resolve_provider_identity()'s default.
            if identity.get("email_verified") is False:
                raise OAuth2ProfileMissingEmailError(
                    f"{provider_name} has not verified this account's email address"
                )
            user = await self._repo.get_user_by_email(email)
            if user is None:
                display_name = identity.get("name") or email.split("@")[0]
                user = await self._repo.create_user(
                    user_id=str(uuid.uuid4()), email=email, password_hash=None,
                    display_name=display_name, role=default_role, email_verified=True,
                )
                is_new_user = True
            await self._repo.create_oauth2_identity(
                identity_id=str(uuid.uuid4()), user_id=user["id"], provider=provider_name,
                provider_user_id=provider_user_id, profile_data=identity,
            )

        if not user["isActive"]:
            raise SessionRevokedError("account is no longer active")

        await self._repo.record_login_success(user["id"])
        await self._enforce_session_limit(user["id"])
        session = await self._issue_session(user=user, now_ms=now_ms, ip=ip, user_agent=user_agent, device_name=None)
        await self._repo.log_audit_event(
            user_id=user["id"], event_type="oauth2_login", event_status="success", ip_address=ip,
            event_message=provider_name,
        )
        session["is_new_user"] = is_new_user
        return session

    # ── Refresh / logout / current-user ──────────────────────────────────

    async def refresh(self, *, refresh_token: str, now_ms: float) -> dict:
        try:
            claims = decode_token(refresh_token, secret=self._config.jwt_secret_key, expected_type="refresh")
        except InvalidTokenError as exc:
            raise SessionRevokedError("refresh token is invalid or expired") from exc

        session = await self._repo.get_session_by_refresh_hash(hash_token(refresh_token))
        if session is None or session["user_id"] != claims["sub"] or session["id"] != claims["session_id"]:
            raise SessionRevokedError("session has been revoked")

        user = await self._repo.get_user_by_id(claims["sub"])
        if user is None or not user["isActive"]:
            raise SessionRevokedError("account is no longer active")

        access_expires_in = self._config.session_config.access_token_expire_minutes * 60
        access_token = create_access_token(
            user_id=user["id"], email=user["email"], role=user["role"], session_id=session["id"],
            secret=self._config.jwt_secret_key, expires_in_seconds=access_expires_in,
        )
        await self._repo.touch_session(session["id"])
        return {"access_token": access_token, "expires_in": access_expires_in}

    async def logout(self, *, access_token: str, now_ms: float) -> None:
        claims = self._decode_access_token(access_token)
        await self._repo.revoke_session(claims["session_id"])

    async def get_current_user(self, *, access_token: str, now_ms: float) -> dict:
        claims = self._decode_access_token(access_token)
        session = await self._repo.get_session_by_id(claims["session_id"])
        if session is None or not session["is_active"]:
            raise SessionRevokedError("session has been revoked")
        user = await self._repo.get_user_by_id(claims["sub"])
        if user is None or not user["isActive"]:
            raise SessionRevokedError("account is no longer active")
        return user

    def _decode_access_token(self, access_token: str) -> dict:
        try:
            return decode_token(access_token, secret=self._config.jwt_secret_key, expected_type="access")
        except InvalidTokenError as exc:
            raise SessionRevokedError("access token is invalid or expired") from exc

    # ── Password management ──────────────────────────────────────────────

    async def _reject_if_password_reused(self, user_id: str, new_password: str, *, current_hash: str | None) -> None:
        """design doc Phase 7 T7.3: don't allow recent passwords. Checks the
        live password plus the last `history_count - 1` retired hashes, so
        `history_count` is the total number of distinct recent passwords a
        user must cycle through before reusing one."""
        history_count = self._config.password_policy.history_count
        if history_count <= 0:
            return
        candidates = [current_hash] if current_hash else []
        candidates += await self._repo.get_password_history(user_id, limit=max(history_count - 1, 0))
        for old_hash in candidates:
            if old_hash and verify_password(new_password, old_hash):
                raise WeakPasswordError(["This password was used recently. Please choose a different password."])

    async def _record_password_history(self, user_id: str, retired_hash: str | None) -> None:
        history_count = self._config.password_policy.history_count
        if history_count <= 0 or not retired_hash:
            return
        await self._repo.record_password_history(user_id, retired_hash, keep_last=history_count)

    async def change_password(
        self, *, user_id: str, current_password: str, new_password: str, now_ms: float | None = None,
    ) -> None:
        stored_hash = await self._repo.get_user_password_hash(user_id)
        if not stored_hash or not verify_password(current_password, stored_hash):
            raise InvalidCredentialsError("current password is incorrect")

        policy = self._config.password_policy
        strength = validate_password_strength(
            new_password,
            min_length=policy.min_length,
            require_uppercase=policy.require_uppercase,
            require_lowercase=policy.require_lowercase,
            require_digits=policy.require_digits,
            require_special=policy.require_special,
        )
        if not strength.valid:
            raise WeakPasswordError(strength.errors)
        await self._reject_if_password_reused(user_id, new_password, current_hash=stored_hash)

        await self._repo.set_password(user_id, hash_password(new_password), now_ms if now_ms is not None else time.time() * 1000)
        await self._repo.revoke_all_sessions_for_user(user_id)
        await self._record_password_history(user_id, stored_hash)

    # ── Email verification & password reset tokens ───────────────────────

    async def request_password_reset(self, *, email: str, now_ms: float, ttl_hours: int = 24) -> str | None:
        """Returns the raw (unhashed) token so the caller can email it, or
        None if there is no account with that email -- callers must still
        report success either way to avoid leaking which emails are
        registered (design doc §7.1.11)."""
        user = await self._repo.get_user_by_email(email)
        if user is None:
            return None
        raw_token = secrets.token_urlsafe(32)
        await self._repo.create_password_reset_token(
            token_id=str(uuid.uuid4()), user_id=user["id"], token_hash=hash_token(raw_token),
            expires_at=now_ms + ttl_hours * 3_600_000,
        )
        await self._email_sender.send(
            build_password_reset_email(to=user["email"], token=raw_token, base_url=self._config.email.app_base_url)
        )
        return raw_token

    async def confirm_password_reset(self, *, token: str, new_password: str, now_ms: float | None = None) -> None:
        policy = self._config.password_policy
        strength = validate_password_strength(
            new_password,
            min_length=policy.min_length,
            require_uppercase=policy.require_uppercase,
            require_lowercase=policy.require_lowercase,
            require_digits=policy.require_digits,
            require_special=policy.require_special,
        )
        if not strength.valid:
            raise WeakPasswordError(strength.errors)

        user_id = await self._repo.consume_password_reset_token(hash_token(token))
        if user_id is None:
            raise InvalidResetTokenError("password reset link is invalid or has expired")
        # The history check needs user_id, which only comes from consuming
        # the token -- unlike the format check above, a reuse rejection here
        # does burn the (single-use) token, requiring a fresh reset email.
        current_hash = await self._repo.get_user_password_hash(user_id)
        await self._reject_if_password_reused(user_id, new_password, current_hash=current_hash)

        await self._repo.set_password(user_id, hash_password(new_password), now_ms if now_ms is not None else time.time() * 1000)
        await self._repo.revoke_all_sessions_for_user(user_id)
        # A completed email-based reset is a stronger identity proof than the
        # failed-attempt lockout guards against; without this, a user who
        # forgot their password stays locked out until the timer expires
        # even though they just proved account ownership via email.
        await self._repo.unlock_account(user_id)
        await self._record_password_history(user_id, current_hash)

    async def request_email_verification(self, *, user_id: str, now_ms: float, ttl_hours: int = 24) -> str:
        raw_token = secrets.token_urlsafe(32)
        await self._repo.create_email_verification_token(
            token_id=str(uuid.uuid4()), user_id=user_id, token_hash=hash_token(raw_token),
            expires_at=now_ms + ttl_hours * 3_600_000,
        )
        user = await self._repo.get_user_by_id(user_id)
        if user is not None:
            await self._email_sender.send(
                build_verification_email(to=user["email"], token=raw_token, base_url=self._config.email.app_base_url)
            )
        return raw_token

    async def confirm_email_verification(self, *, token: str) -> None:
        user_id = await self._repo.consume_email_verification_token(hash_token(token))
        if user_id is None:
            raise InvalidResetTokenError("verification link is invalid or has expired")
        await self._repo.update_user(user_id, email_verified=True)

    # ── Admin user management (design doc §7.2) ──────────────────────────

    async def admin_create_user(
        self, *, email: str, display_name: str, username: str | None = None,
        role: str = "learner", created_by: str | None = None,
    ) -> tuple[dict, str]:
        """Returns (user, temporary_password). The temporary password is
        returned exactly once here for the caller to relay to the new user
        (e.g. by email) -- it is never retrievable again afterward."""
        temp_password = generate_temporary_password()
        user = await self._repo.create_user(
            user_id=str(uuid.uuid4()), email=email, password_hash=hash_password(temp_password),
            display_name=display_name, username=username, role=role, created_by=created_by,
            email_verified=True, requires_password_change=True,
        )
        await self._repo.log_audit_event(
            user_id=user["id"], event_type="admin_create_user", event_status="success",
            event_message=f"created by {created_by}" if created_by else None,
        )
        await self._email_sender.send(
            build_welcome_email(
                to=user["email"], display_name=user["displayName"], temporary_password=temp_password,
                base_url=self._config.email.app_base_url,
            )
        )
        return user, temp_password

    async def admin_bulk_import_users(self, *, rows: list[dict], created_by: str | None = None) -> dict:
        """CSV bulk import (design doc §7.2.9). Each row: email, display_name,
        optional username/role. Bad rows are skipped and reported rather than
        aborting the whole import, so one typo doesn't block 500 good rows."""
        if len(rows) > MAX_BULK_IMPORT_ROWS:
            raise BulkImportTooLargeError(f"cannot import more than {MAX_BULK_IMPORT_ROWS} rows at once")

        imported = 0
        skipped = 0
        errors: list[dict] = []

        for index, row in enumerate(rows, start=1):
            email = (row.get("email") or "").strip()
            display_name = (row.get("display_name") or "").strip()
            username = (row.get("username") or "").strip() or None
            role = (row.get("role") or "learner").strip() or "learner"

            if not email:
                skipped += 1
                errors.append({"row": index, "email": email, "reason": "Missing email"})
                continue
            if not display_name:
                skipped += 1
                errors.append({"row": index, "email": email, "reason": "Missing display_name"})
                continue
            if role not in ALLOWED_ROLES:
                skipped += 1
                errors.append({"row": index, "email": email, "reason": f"Invalid role: {role!r}"})
                continue

            try:
                await self.admin_create_user(
                    email=email, display_name=display_name, username=username, role=role, created_by=created_by,
                )
                imported += 1
            except DuplicateEmailError:
                skipped += 1
                errors.append({"row": index, "email": email, "reason": "Email already exists"})
            except DuplicateUsernameError:
                skipped += 1
                errors.append({"row": index, "email": email, "reason": "Username already taken"})

        return {"imported": imported, "skipped": skipped, "errors": errors}

    async def admin_reset_password(self, *, user_id: str, now_ms: float | None = None) -> str:
        temp_password = generate_temporary_password()
        await self._repo.set_password(user_id, hash_password(temp_password), now_ms if now_ms is not None else time.time() * 1000)
        await self._repo.update_user(user_id, requires_password_change=True)
        await self._repo.revoke_all_sessions_for_user(user_id)
        await self._repo.log_audit_event(user_id=user_id, event_type="admin_reset_password", event_status="success")
        return temp_password

    async def admin_update_user(
        self, *, user_id: str, display_name: str | None = None, role: str | None = None,
        is_active: bool | None = None,
    ) -> dict | None:
        fields = {}
        if display_name is not None:
            fields["display_name"] = display_name
        if role is not None:
            fields["role"] = role
        if is_active is not None:
            fields["is_active"] = is_active
        return await self._repo.update_user(user_id, **fields)

    async def admin_disable_user(self, *, user_id: str) -> None:
        await self._repo.update_user(user_id, is_active=False)
        await self._repo.revoke_all_sessions_for_user(user_id)
        await self._repo.log_audit_event(user_id=user_id, event_type="admin_disable_user", event_status="success")

    async def admin_enable_user(self, *, user_id: str) -> None:
        await self._repo.update_user(user_id, is_active=True)
        await self._repo.log_audit_event(user_id=user_id, event_type="admin_enable_user", event_status="success")

    async def admin_unlock_user(self, *, user_id: str) -> None:
        await self._repo.unlock_account(user_id)
        await self._repo.log_audit_event(user_id=user_id, event_type="admin_unlock_user", event_status="success")

    async def admin_delete_user(self, *, user_id: str) -> bool:
        deleted = await self._repo.soft_delete_user(user_id)
        if deleted:
            await self._repo.revoke_all_sessions_for_user(user_id)
            await self._repo.log_audit_event(user_id=user_id, event_type="admin_delete_user", event_status="success")
        return deleted

    async def get_user(self, user_id: str) -> dict | None:
        return await self._repo.get_user_by_id(user_id)

    async def get_user_by_email(self, email: str) -> dict | None:
        return await self._repo.get_user_by_email(email)

    async def list_users(
        self, *, role: str | None = None, is_active: bool | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict], int]:
        return await self._repo.list_users(role=role, is_active=is_active, limit=limit, offset=offset)

    async def list_audit_events(
        self, *, user_id: str | None = None, event_type: str | None = None, limit: int = 50,
    ) -> list[dict]:
        return await self._repo.list_audit_events(user_id=user_id, event_type=event_type, limit=limit)

    async def count_users(self) -> int:
        return await self._repo.count_users()

    # ── Self-service profile & sessions (design doc §7.3) ────────────────

    async def update_profile(
        self, *, user_id: str, display_name: str | None = None, bio: str | None = None,
        preferred_topics: list[str] | None = None,
    ) -> dict | None:
        fields = {}
        if display_name is not None:
            fields["display_name"] = display_name
        if bio is not None:
            fields["bio"] = bio
        if preferred_topics is not None:
            fields["preferred_topics"] = preferred_topics
        return await self._repo.update_user(user_id, **fields)

    async def list_sessions(self, *, user_id: str) -> list[dict]:
        return await self._repo.list_sessions_for_user(user_id)

    async def revoke_session(self, *, user_id: str, session_id: str) -> bool:
        session = await self._repo.get_session_by_id(session_id)
        if session is None or session["user_id"] != user_id:
            # Reads as "not found" rather than "forbidden" so a user can't
            # use this endpoint to probe whether some other session id
            # exists at all.
            return False
        return await self._repo.revoke_session(session_id)


def _to_epoch_ms(value) -> float:
    """`locked_until`/expiry values round-trip through the repo as either a
    plain epoch-ms float (tests, in-memory repo) or a datetime-like object
    (asyncpg TIMESTAMPTZ rows); normalize both to epoch milliseconds."""
    if isinstance(value, (int, float)):
        return float(value)
    return value.timestamp() * 1000
