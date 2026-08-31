"""CLI admin bootstrap (design doc §18.2) -- an alternative to the
INITIAL_ADMIN_EMAIL/INITIAL_ADMIN_PASSWORD env vars for operators who don't
want a real password sitting in shell history/.env files.

    python -m server.scripts.create_admin --email admin@example.com --display-name "System Administrator"

Prompts for the password interactively (no terminal echo) and exits
non-zero with a clear message on any failure.
"""

import argparse
import asyncio
import getpass
import sys

from server.auth.bootstrap import create_admin_user
from server.auth.config import auth_config
from server.auth.service import WeakPasswordError
from server.db.database import Database, DuplicateEmailError, DuplicateUsernameError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an admin account (design doc §18.2).")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--username", default=None)
    return parser.parse_args(argv)


def read_password(prompt_fn=getpass.getpass) -> str:
    """Loops until the two entries match, matching a typical `passwd`-style
    confirmation prompt rather than silently accepting a typo."""
    while True:
        password = prompt_fn("Password: ")
        confirm = prompt_fn("Confirm password: ")
        if password == confirm:
            return password
        print("Passwords do not match. Please try again.", file=sys.stderr)


async def create_admin_via_cli(
    repo, *, email: str, display_name: str, password: str, username: str | None = None,
) -> int:
    """Returns a process exit code (0 success, 1 failure) rather than
    raising, so `main()` can just `sys.exit()` it."""
    try:
        user = await create_admin_user(
            repo, auth_config, email=email, display_name=display_name, password=password, username=username,
        )
    except WeakPasswordError as exc:
        print(f"Password does not meet the policy: {'; '.join(exc.errors)}", file=sys.stderr)
        return 1
    except DuplicateEmailError:
        print(f"A user with email {email!r} already exists.", file=sys.stderr)
        return 1
    except DuplicateUsernameError:
        print(f"Username {username!r} is already taken.", file=sys.stderr)
        return 1

    print(f"Created admin account {user['email']} (id={user['id']}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    password = read_password()

    async def _run() -> int:
        repo = Database()
        await repo.connect()
        try:
            return await create_admin_via_cli(
                repo, email=args.email, display_name=args.display_name,
                username=args.username, password=password,
            )
        finally:
            await repo.disconnect()

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
