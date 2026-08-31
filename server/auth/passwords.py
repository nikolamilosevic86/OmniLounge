"""Password hashing and strength validation (design doc §10.1, §4.1).

Hashing uses bcrypt directly (not passlib): passlib's bcrypt backend has had
real compatibility breaks with newer bcrypt releases, and bcrypt itself is
maintained by the same team as `cryptography`. Cost factor 12 matches the
design doc's recommendation.
"""

from dataclasses import dataclass, field
import re
import secrets

import bcrypt

# bcrypt only uses the first 72 bytes of the input and silently ignores the
# rest, so any password past that length is truncated to something shorter
# than the user thinks they set. Reject it outright instead.
MAX_PASSWORD_BYTES = 72

DEFAULT_MIN_LENGTH = 8
DEFAULT_COST_FACTOR = 12

# A short, well-known blocklist of the most commonly breached passwords.
# Not exhaustive (a real deployment would want a much bigger corpus, e.g.
# the top 10k from Have I Been Pwned), but blocks the most obvious choices.
_COMMON_PASSWORDS = frozenset(
    p.lower()
    for p in (
        "password", "password1", "password123", "123456", "12345678",
        "qwerty", "letmein", "welcome", "admin", "iloveyou", "monkey",
        "dragon", "football", "abc123", "111111", "123123",
    )
)


def _matches_common_password(password: str) -> bool:
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS:
        return True
    # Strip trailing punctuation/digits some users tack on (e.g.
    # "Password123!") so the underlying common word is still caught.
    stripped = re.sub(r"[^a-z]+$", "", lowered)
    return stripped in _COMMON_PASSWORDS


def hash_password(password: str, cost_factor: int = DEFAULT_COST_FACTOR) -> str:
    if not password:
        raise ValueError("password must not be empty")
    encoded = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=cost_factor)
    return bcrypt.hashpw(encoded, salt).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    """Never raises: a malformed/corrupted stored hash must read as
    'password does not match', not crash the login endpoint."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def needs_rehash(stored_hash: str, cost_factor: int = DEFAULT_COST_FACTOR) -> bool:
    """True if `stored_hash` was hashed with a weaker cost factor than the
    current policy, so callers can transparently upgrade it on next login."""
    try:
        current_cost = int(stored_hash.split("$")[2])
    except (IndexError, ValueError):
        return True
    return current_cost < cost_factor


@dataclass
class PasswordStrengthResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_password_strength(
    password: str,
    *,
    min_length: int = DEFAULT_MIN_LENGTH,
    require_uppercase: bool = True,
    require_lowercase: bool = True,
    require_digits: bool = True,
    require_special: bool = True,
    special_chars: str = "!@#$%^&*()_+-=[]{}|;:,.<>?",
    block_common: bool = True,
    username: str | None = None,
) -> PasswordStrengthResult:
    errors: list[str] = []

    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        errors.append(f"Password must be {MAX_PASSWORD_BYTES} bytes or fewer.")
    if len(password) < min_length:
        errors.append(f"Password must be at least {min_length} characters (length).")
    if require_uppercase and not any(c.isupper() for c in password):
        errors.append("Password must contain an uppercase letter.")
    if require_lowercase and not any(c.islower() for c in password):
        errors.append("Password must contain a lowercase letter.")
    if require_digits and not any(c.isdigit() for c in password):
        errors.append("Password must contain a digit.")
    if require_special and not any(c in special_chars for c in password):
        errors.append("Password must contain a special character.")
    if block_common and _matches_common_password(password):
        errors.append("This password is too common. Please choose another.")
    if username and username.lower() in password.lower():
        errors.append("Password must not contain your username.")

    return PasswordStrengthResult(valid=len(errors) == 0, errors=errors)


def generate_temporary_password(length: int = 16) -> str:
    """Random password for admin-created accounts (design doc §4.2, §7.2.1),
    engineered to satisfy validate_password_strength()'s default policy: at
    least one of each required character class, drawn with `secrets` (not
    `random`) since this value is a real credential, not test data."""
    alphabet_upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O to avoid visual ambiguity
    alphabet_lower = "abcdefghijkmnpqrstuvwxyz"
    alphabet_digits = "23456789"
    alphabet_special = "!@#$%^&*"
    required = [
        secrets.choice(alphabet_upper), secrets.choice(alphabet_lower),
        secrets.choice(alphabet_digits), secrets.choice(alphabet_special),
    ]
    all_chars = alphabet_upper + alphabet_lower + alphabet_digits + alphabet_special
    remaining = [secrets.choice(all_chars) for _ in range(max(length - len(required), 0))]
    chars = required + remaining
    # secrets.SystemRandom().shuffle so the four guaranteed-class characters
    # aren't predictably in the first four positions.
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars[:length])
