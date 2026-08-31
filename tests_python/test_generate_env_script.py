"""Unit tests for scripts/generate_env.py: the .env bootstrap helper used
by run.sh / run.bat so a fresh checkout works with zero manual editing."""

from scripts.generate_env import generate_env


class TestGenerateEnv:
    def test_creates_env_from_example_with_a_real_jwt_secret(self, tmp_path):
        example = tmp_path / ".env.example"
        example.write_text("JWT_SECRET_KEY=\nAUTH_ENABLE_LOCAL_REGISTRATION=false\nPORT=8000\n")
        env_path = tmp_path / ".env"

        created = generate_env(env_path=env_path, example_path=example)

        assert created is True
        text = env_path.read_text()
        assert "JWT_SECRET_KEY=" in text
        secret_line = next(line for line in text.splitlines() if line.startswith("JWT_SECRET_KEY="))
        assert len(secret_line.split("=", 1)[1]) >= 32
        assert "AUTH_ENABLE_LOCAL_REGISTRATION=true" in text
        assert "PORT=8000" in text

    def test_does_not_overwrite_an_existing_env(self, tmp_path):
        example = tmp_path / ".env.example"
        example.write_text("JWT_SECRET_KEY=\n")
        env_path = tmp_path / ".env"
        env_path.write_text("JWT_SECRET_KEY=already-set-by-the-user\n")

        created = generate_env(env_path=env_path, example_path=example)

        assert created is False
        assert env_path.read_text() == "JWT_SECRET_KEY=already-set-by-the-user\n"

    def test_generated_secret_is_different_each_time(self, tmp_path):
        example = tmp_path / ".env.example"
        example.write_text("JWT_SECRET_KEY=\n")

        env_a = tmp_path / "a" / ".env"
        env_a.parent.mkdir()
        env_b = tmp_path / "b" / ".env"
        env_b.parent.mkdir()

        generate_env(env_path=env_a, example_path=example)
        generate_env(env_path=env_b, example_path=example)

        assert env_a.read_text() != env_b.read_text()
