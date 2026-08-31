"""Master authentication configuration (design doc §5). Computed at import
time from environment variables, mirroring server/config.py's pattern.

The design doc's own example config nests everything under a single
`AuthConfig` dataclass; this module keeps that shape but loads it as a
module-level `auth_config` singleton (like `server/config.py`'s bare
module-level constants) rather than a class users must construct
themselves, so the rest of the codebase can just `from server.auth.config
import auth_config`.
"""

import os
from dataclasses import dataclass, field


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _optional_int_env(name: str) -> int | None:
    raw = os.getenv(name)
    # A blank string (not just an unset var) must also mean "disabled" --
    # that's how a .env file conventionally represents "no value set" for
    # a key that's still listed for discoverability (see .env.example).
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


@dataclass
class PasswordPolicy:
    min_length: int = 8
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digits: bool = True
    require_special: bool = True
    # design doc Phase 7 T7.3 "password history"; 0 disables the check.
    history_count: int = 5
    # design doc §5.1 PasswordPolicy.expiry_days; None disables the check.
    expiry_days: int | None = None


@dataclass
class SessionConfig:
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    max_sessions_per_user: int = 5


@dataclass
class EmailConfig:
    """SMTP delivery settings (design doc §5.2, §20). `smtp_host` unset means
    no real mail provider is configured, so callers fall back to logging
    emails instead of sending them (see server/auth/email.py)."""

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    from_address: str = "no-reply@omnilaunge.local"
    app_base_url: str = "http://localhost:8000"

    @property
    def is_configured(self) -> bool:
        return bool(self.smtp_host)


@dataclass
class AuthConfig:
    jwt_secret_key: str

    enable_local_registration: bool = False
    enable_local_login: bool = True
    admin_only_registration: bool = False
    require_email_verification: bool = False
    # Off by default (design doc §16): the existing real-time game is fully
    # anonymous. Flipping this on requires every Socket.IO client to also
    # send a valid access token at connect time -- opt-in only.
    require_socket_auth: bool = False
    # On by default, matching this app's original anonymous-play design: an
    # unauthenticated visitor can create an avatar and join a room without
    # ever registering/logging in. Set to False to require a real account
    # for anyone to use the app at all ("Continue as a guest" is hidden on
    # the login page, and the main game redirects an anonymous visitor to
    # the login page instead of showing the creator screen).
    allow_guest_access: bool = True

    password_policy: PasswordPolicy = field(default_factory=PasswordPolicy)
    session_config: SessionConfig = field(default_factory=SessionConfig)
    email: EmailConfig = field(default_factory=EmailConfig)

    registration_rate_limit_per_hour: int = 10
    login_rate_limit_per_hour: int = 100
    failed_login_lockout_threshold: int = 5
    failed_login_lockout_minutes: int = 15

    def __post_init__(self) -> None:
        if len(self.jwt_secret_key) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY must be at least 32 characters. Generate one with, "
                "e.g., `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`."
            )
        if self.enable_local_registration and self.admin_only_registration:
            raise RuntimeError(
                "AUTH_ENABLE_LOCAL_REGISTRATION and AUTH_ADMIN_ONLY_REGISTRATION "
                "are mutually exclusive: open self-registration and admin-only "
                "account creation cannot both be active."
            )


def _load_auth_config() -> AuthConfig:
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is required to start the server. Generate one with, "
            "e.g., `python -c \"import secrets; print(secrets.token_urlsafe(48))\"` "
            "and set it in the environment."
        )
    return AuthConfig(
        jwt_secret_key=secret,
        enable_local_registration=_bool_env("AUTH_ENABLE_LOCAL_REGISTRATION", False),
        enable_local_login=_bool_env("AUTH_ENABLE_LOCAL_LOGIN", True),
        admin_only_registration=_bool_env("AUTH_ADMIN_ONLY_REGISTRATION", False),
        require_email_verification=_bool_env("AUTH_REQUIRE_EMAIL_VERIFICATION", False),
        require_socket_auth=_bool_env("AUTH_REQUIRE_SOCKET_AUTH", False),
        allow_guest_access=_bool_env("AUTH_ALLOW_GUEST_ACCESS", True),
        password_policy=PasswordPolicy(
            min_length=_int_env("AUTH_PASSWORD_MIN_LENGTH", 8),
            require_uppercase=_bool_env("AUTH_PASSWORD_REQUIRE_UPPERCASE", True),
            require_lowercase=_bool_env("AUTH_PASSWORD_REQUIRE_LOWERCASE", True),
            require_digits=_bool_env("AUTH_PASSWORD_REQUIRE_DIGITS", True),
            require_special=_bool_env("AUTH_PASSWORD_REQUIRE_SPECIAL", True),
            history_count=_int_env("AUTH_PASSWORD_HISTORY_COUNT", 5),
            expiry_days=_optional_int_env("AUTH_PASSWORD_EXPIRY_DAYS"),
        ),
        session_config=SessionConfig(
            access_token_expire_minutes=_int_env("AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", 30),
            refresh_token_expire_days=_int_env("AUTH_REFRESH_TOKEN_EXPIRE_DAYS", 7),
            max_sessions_per_user=_int_env("AUTH_MAX_SESSIONS_PER_USER", 5),
        ),
        email=EmailConfig(
            smtp_host=os.getenv("SMTP_SERVER") or None,
            smtp_port=_int_env("SMTP_PORT", 587),
            smtp_username=os.getenv("SMTP_USERNAME") or None,
            smtp_password=os.getenv("SMTP_PASSWORD") or None,
            smtp_use_tls=_bool_env("SMTP_USE_TLS", True),
            from_address=os.getenv("EMAIL_FROM_ADDRESS") or os.getenv("ADMIN_EMAIL") or "no-reply@omnilaunge.local",
            app_base_url=os.getenv("APP_BASE_URL", "http://localhost:8000"),
        ),
        registration_rate_limit_per_hour=_int_env("AUTH_REGISTRATION_RATE_LIMIT_PER_HOUR", 10),
        login_rate_limit_per_hour=_int_env("AUTH_LOGIN_RATE_LIMIT_PER_HOUR", 100),
        failed_login_lockout_threshold=_int_env("AUTH_FAILED_LOGIN_LOCKOUT_THRESHOLD", 5),
        failed_login_lockout_minutes=_int_env("AUTH_FAILED_LOGIN_LOCKOUT_MINUTES", 15),
    )


auth_config = _load_auth_config()
