"""Initial admin account bootstrapping on a fresh deployment (design doc
§18). Called once from server/main.py's lifespan, after db.connect().
"""

import logging
import os
import uuid

from server.auth.config import AuthConfig
from server.auth.passwords import hash_password, validate_password_strength
from server.auth.service import WeakPasswordError

logger = logging.getLogger(__name__)


async def bootstrap_initial_admin(repo, config: AuthConfig) -> dict | None:
    """Creates the first admin account from INITIAL_ADMIN_EMAIL /
    INITIAL_ADMIN_PASSWORD env vars if the users table is empty. Returns the
    created user, or None if nothing was created (already-populated
    database, missing env vars, or a password too weak to accept).

    Deliberately never raises: a bootstrap misconfiguration should not take
    the whole server down, since a fresh deployment could still be reached
    over the (would-be) admin-only CLI/SQL path.
    """
    email = os.getenv("INITIAL_ADMIN_EMAIL")
    password = os.getenv("INITIAL_ADMIN_PASSWORD")
    if not email or not password:
        return None

    if await repo.count_users() > 0:
        return None

    policy = config.password_policy
    strength = validate_password_strength(
        password,
        min_length=policy.min_length,
        require_uppercase=policy.require_uppercase,
        require_lowercase=policy.require_lowercase,
        require_digits=policy.require_digits,
        require_special=policy.require_special,
    )
    if not strength.valid:
        logger.error(
            "INITIAL_ADMIN_PASSWORD does not meet the password policy (%s); "
            "skipping initial admin creation. Fix the password and restart.",
            "; ".join(strength.errors),
        )
        return None

    display_name = os.getenv("INITIAL_ADMIN_DISPLAY_NAME") or "System Administrator"
    user = await repo.create_user(
        user_id=str(uuid.uuid4()), email=email, password_hash=hash_password(password),
        display_name=display_name, role="admin", email_verified=True, requires_password_change=True,
    )
    user = await repo.update_user(user["id"], is_admin=True)
    logger.warning("Created initial admin account for %s. Remove INITIAL_ADMIN_* env vars after first login.", email)
    return user


async def create_admin_user(
    repo, config: AuthConfig, *, email: str, display_name: str, password: str, username: str | None = None,
) -> dict:
    """Creates an admin account with an operator-chosen password (design
    doc §18.2's CLI bootstrap script). Unlike bootstrap_initial_admin, this
    raises on failure (WeakPasswordError, DuplicateEmailError,
    DuplicateUsernameError) so a CLI caller can report a clear error instead
    of silently doing nothing."""
    policy = config.password_policy
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

    user = await repo.create_user(
        user_id=str(uuid.uuid4()), email=email, password_hash=hash_password(password),
        display_name=display_name, username=username, role="admin",
        email_verified=True, requires_password_change=False,
    )
    return await repo.update_user(user["id"], is_admin=True)
