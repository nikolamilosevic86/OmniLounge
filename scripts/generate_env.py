"""Bootstraps a local .env from .env.example, filling in a random dev JWT
secret and enabling open registration -- so `./run.sh` / `run.bat` (or any
manual `python scripts/generate_env.py`) gives a fresh checkout a working
.env with zero manual editing, without ever putting a real secret in the
committed .env.example template. Safe to run repeatedly: a no-op if .env
already exists, so it never clobbers an existing configuration.
"""

import re
import secrets
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"


def generate_env(env_path: Path = ENV_PATH, example_path: Path = EXAMPLE_PATH) -> bool:
    """Returns True if a new .env was created, False if one already existed."""
    if env_path.exists():
        return False

    shutil.copyfile(example_path, env_path)
    text = env_path.read_text()
    text = re.sub(
        r"^JWT_SECRET_KEY=.*$", f"JWT_SECRET_KEY={secrets.token_urlsafe(48)}", text, count=1, flags=re.M,
    )
    text = re.sub(
        r"^AUTH_ENABLE_LOCAL_REGISTRATION=.*$", "AUTH_ENABLE_LOCAL_REGISTRATION=true", text, count=1, flags=re.M,
    )
    env_path.write_text(text)
    return True


def main() -> None:
    if generate_env():
        print("Created .env from .env.example with a random dev JWT secret and local registration enabled.")
    else:
        print(".env already exists -- leaving it untouched.")


if __name__ == "__main__":
    main()
