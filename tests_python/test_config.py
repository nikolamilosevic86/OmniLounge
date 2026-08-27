"""Unit tests for server/config.py.

Config values are computed at import time from environment variables, so
these tests reload the module with controlled env vars to verify both the
defaults and the env-var override/parsing behavior. Each test restores the
module to its default (no env vars set) state before returning so it can't
leak state into other tests that import server.config."""

import importlib

import server.config as config_module


class TestConfigDefaults:
    def test_defaults_when_no_env_vars_are_set(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("PORT", raising=False)
        monkeypatch.delenv("MOVE_SPEED", raising=False)
        monkeypatch.delenv("TICK_RATE", raising=False)

        try:
            reloaded = importlib.reload(config_module)
            assert reloaded.DATABASE_URL == "postgresql://omnilaunge:omnilaunge@localhost:5432/omnilaunge"
            assert reloaded.PORT == 8000
            assert reloaded.MOVE_SPEED == 4.0
            assert reloaded.TICK_RATE == 30.0
            assert reloaded.BUBBLE_DURATION_MS == 6000
            assert reloaded.MAX_MESSAGES == 200
        finally:
            monkeypatch.undo()
            importlib.reload(config_module)


class TestConfigEnvOverrides:
    def test_env_vars_override_and_coerce_types(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@testhost:5432/testdb")
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("MOVE_SPEED", "6.5")
        monkeypatch.setenv("TICK_RATE", "60")

        try:
            reloaded = importlib.reload(config_module)
            assert reloaded.DATABASE_URL == "postgresql://test:test@testhost:5432/testdb"
            assert reloaded.PORT == 9000
            assert isinstance(reloaded.PORT, int)
            assert reloaded.MOVE_SPEED == 6.5
            assert isinstance(reloaded.MOVE_SPEED, float)
            assert reloaded.TICK_RATE == 60.0
        finally:
            monkeypatch.undo()
            importlib.reload(config_module)
