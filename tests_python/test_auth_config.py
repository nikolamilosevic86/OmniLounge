"""Unit tests for server/auth/config.py: env-driven AuthConfig loading
(design doc §5). Follows the reload-with-controlled-env-vars pattern used
by tests_python/test_config.py."""

import importlib

import server.auth.config as auth_config_module

ENV_VARS = [
    "AUTH_ENABLE_LOCAL_REGISTRATION",
    "AUTH_ENABLE_LOCAL_LOGIN",
    "AUTH_ADMIN_ONLY_REGISTRATION",
    "AUTH_REQUIRE_EMAIL_VERIFICATION",
    "AUTH_REQUIRE_SOCKET_AUTH",
    "AUTH_ALLOW_GUEST_ACCESS",
    "AUTH_PASSWORD_MIN_LENGTH",
    "AUTH_PASSWORD_REQUIRE_UPPERCASE",
    "AUTH_PASSWORD_REQUIRE_SPECIAL",
    "AUTH_PASSWORD_HISTORY_COUNT",
    "AUTH_PASSWORD_EXPIRY_DAYS",
    "AUTH_ACCESS_TOKEN_EXPIRE_MINUTES",
    "AUTH_REFRESH_TOKEN_EXPIRE_DAYS",
    "AUTH_MAX_SESSIONS_PER_USER",
    "AUTH_REGISTRATION_RATE_LIMIT_PER_HOUR",
    "AUTH_LOGIN_RATE_LIMIT_PER_HOUR",
    "AUTH_FAILED_LOGIN_LOCKOUT_THRESHOLD",
    "AUTH_FAILED_LOGIN_LOCKOUT_MINUTES",
    "SMTP_SERVER",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_USE_TLS",
    "EMAIL_FROM_ADDRESS",
    "ADMIN_EMAIL",
    "APP_BASE_URL",
    "JWT_SECRET_KEY",
]


def reload_with(monkeypatch, **env):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    try:
        return importlib.reload(auth_config_module)
    finally:
        pass


class TestDefaults:
    def test_safe_defaults_when_nothing_is_configured(self, monkeypatch):
        reloaded = reload_with(monkeypatch, JWT_SECRET_KEY="x" * 32)
        cfg = reloaded.auth_config
        try:
            # Registration closed and email verification off by default is the
            # conservative choice: an operator must opt in to open signup.
            assert cfg.enable_local_registration is False
            assert cfg.enable_local_login is True
            assert cfg.admin_only_registration is False
            assert cfg.require_email_verification is False
            assert cfg.require_socket_auth is False
            assert cfg.allow_guest_access is True
            assert cfg.password_policy.min_length == 8
            assert cfg.password_policy.require_uppercase is True
            assert cfg.password_policy.history_count == 5
            assert cfg.password_policy.expiry_days is None
            assert cfg.session_config.access_token_expire_minutes == 30
            assert cfg.session_config.refresh_token_expire_days == 7
            assert cfg.session_config.max_sessions_per_user == 5
            assert cfg.registration_rate_limit_per_hour == 10
            assert cfg.login_rate_limit_per_hour == 100
            assert cfg.failed_login_lockout_threshold == 5
            assert cfg.failed_login_lockout_minutes == 15
            assert cfg.email.is_configured is False
            assert cfg.email.smtp_host is None
            assert cfg.email.from_address == "no-reply@omnilaunge.local"
            assert cfg.email.app_base_url == "http://localhost:8000"
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_missing_jwt_secret_raises_at_import_time(self, monkeypatch):
        for name in ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        try:
            import pytest as _pytest
            with _pytest.raises(RuntimeError):
                importlib.reload(auth_config_module)
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_short_jwt_secret_raises_at_import_time(self, monkeypatch):
        import pytest as _pytest
        monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
        try:
            with _pytest.raises(RuntimeError):
                importlib.reload(auth_config_module)
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)


class TestEnvOverrides:
    def test_env_vars_override_and_coerce_types(self, monkeypatch):
        reloaded = reload_with(
            monkeypatch,
            JWT_SECRET_KEY="y" * 40,
            AUTH_ADMIN_ONLY_REGISTRATION="true",
            AUTH_PASSWORD_MIN_LENGTH="12",
            AUTH_ACCESS_TOKEN_EXPIRE_MINUTES="60",
            AUTH_REFRESH_TOKEN_EXPIRE_DAYS="30",
            AUTH_LOGIN_RATE_LIMIT_PER_HOUR="200",
        )
        cfg = reloaded.auth_config
        try:
            assert cfg.enable_local_registration is False
            assert cfg.admin_only_registration is True
            assert cfg.password_policy.min_length == 12
            assert isinstance(cfg.password_policy.min_length, int)
            assert cfg.session_config.access_token_expire_minutes == 60
            assert cfg.session_config.refresh_token_expire_days == 30
            assert cfg.login_rate_limit_per_hour == 200
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_admin_only_and_open_registration_cannot_both_be_enabled(self, monkeypatch):
        import pytest as _pytest
        monkeypatch.setenv("JWT_SECRET_KEY", "z" * 32)
        monkeypatch.setenv("AUTH_ENABLE_LOCAL_REGISTRATION", "true")
        monkeypatch.setenv("AUTH_ADMIN_ONLY_REGISTRATION", "true")
        try:
            with _pytest.raises(RuntimeError):
                importlib.reload(auth_config_module)
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_boolean_env_parsing_is_case_insensitive(self, monkeypatch):
        reloaded = reload_with(monkeypatch, JWT_SECRET_KEY="a" * 32, AUTH_ENABLE_LOCAL_REGISTRATION="TRUE")
        try:
            assert reloaded.auth_config.enable_local_registration is True
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_socket_auth_can_be_enabled_via_env_var(self, monkeypatch):
        reloaded = reload_with(monkeypatch, JWT_SECRET_KEY="c" * 32, AUTH_REQUIRE_SOCKET_AUTH="true")
        try:
            assert reloaded.auth_config.require_socket_auth is True
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_guest_access_can_be_disabled_via_env_var(self, monkeypatch):
        reloaded = reload_with(monkeypatch, JWT_SECRET_KEY="g" * 32, AUTH_ALLOW_GUEST_ACCESS="false")
        try:
            assert reloaded.auth_config.allow_guest_access is False
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_password_history_count_is_configurable(self, monkeypatch):
        reloaded = reload_with(monkeypatch, JWT_SECRET_KEY="d" * 32, AUTH_PASSWORD_HISTORY_COUNT="3")
        try:
            assert reloaded.auth_config.password_policy.history_count == 3
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_password_expiry_days_is_configurable(self, monkeypatch):
        reloaded = reload_with(monkeypatch, JWT_SECRET_KEY="e" * 32, AUTH_PASSWORD_EXPIRY_DAYS="90")
        try:
            assert reloaded.auth_config.password_policy.expiry_days == 90
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_blank_optional_env_vars_are_treated_as_unset(self, monkeypatch):
        """A .env file conventionally lists an unused key as `KEY=` (blank),
        not omitted entirely -- must not crash, and must behave exactly
        like the var being absent."""
        reloaded = reload_with(
            monkeypatch, JWT_SECRET_KEY="f" * 32,
            AUTH_PASSWORD_EXPIRY_DAYS="", AUTH_PASSWORD_HISTORY_COUNT="",
        )
        try:
            assert reloaded.auth_config.password_policy.expiry_days is None
            assert reloaded.auth_config.password_policy.history_count == 5
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)

    def test_smtp_env_vars_configure_email_delivery(self, monkeypatch):
        reloaded = reload_with(
            monkeypatch,
            JWT_SECRET_KEY="b" * 32,
            SMTP_SERVER="smtp.example.com",
            SMTP_PORT="2525",
            SMTP_USERNAME="user",
            SMTP_PASSWORD="pass",
            EMAIL_FROM_ADDRESS="hello@example.com",
            APP_BASE_URL="https://app.example.com",
        )
        try:
            cfg = reloaded.auth_config
            assert cfg.email.is_configured is True
            assert cfg.email.smtp_host == "smtp.example.com"
            assert cfg.email.smtp_port == 2525
            assert cfg.email.smtp_username == "user"
            assert cfg.email.smtp_password == "pass"
            assert cfg.email.from_address == "hello@example.com"
            assert cfg.email.app_base_url == "https://app.example.com"
        finally:
            monkeypatch.undo()
            importlib.reload(auth_config_module)
