"""JWT access/refresh token issuance and validation (design doc §17).

Uses PyJWT with HS256. The design doc's §17 discusses RS256 + key rotation
for multi-service deployments; this app is a single FastAPI process with no
downstream service that needs to verify tokens independently, so HS256 with
a single secret is the right amount of complexity -- RS256 support can be
added later without changing this module's public API.
"""

import hashlib
import time
import uuid

import jwt

ISSUER = "omnilaunge"


class InvalidTokenError(Exception):
    """Token is malformed, has a bad signature, wrong type, or wrong issuer."""


class TokenExpiredError(InvalidTokenError):
    """Token is otherwise well-formed but its `exp` claim has passed."""


def _encode(claims: dict, secret: str) -> str:
    return jwt.encode(claims, secret, algorithm="HS256")


def create_access_token(
    *, user_id: str, email: str, role: str, session_id: str, secret: str,
    expires_in_seconds: int, issuer: str = ISSUER,
) -> str:
    now = int(time.time())
    claims = {
        "sub": user_id,
        "email": email,
        "role": role,
        "session_id": session_id,
        "type": "access",
        "iat": now,
        "exp": now + expires_in_seconds,
        "iss": issuer,
        "jti": str(uuid.uuid4()),
    }
    return _encode(claims, secret)


def create_refresh_token(
    *, user_id: str, session_id: str, secret: str, expires_in_seconds: int, issuer: str = ISSUER,
) -> str:
    now = int(time.time())
    claims = {
        "sub": user_id,
        "session_id": session_id,
        "type": "refresh",
        "iat": now,
        "exp": now + expires_in_seconds,
        "iss": issuer,
        "jti": str(uuid.uuid4()),
    }
    return _encode(claims, secret)


def decode_token(token: str, *, secret: str, expected_type: str | None = None, issuer: str = ISSUER) -> dict:
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], issuer=issuer)
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("token has expired") from exc
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if expected_type is not None and claims.get("type") != expected_type:
        raise InvalidTokenError(f"expected a {expected_type} token, got {claims.get('type')!r}")
    return claims


def hash_token(token: str) -> str:
    """One-way digest stored in the DB in place of the raw token (design doc
    §6.2), so a leaked `user_sessions` row can't be replayed as a live
    session. SHA-256 (not bcrypt) is appropriate here: JWTs are already
    high-entropy random-looking strings, not low-entropy human passwords, so
    there is nothing for a slow, salted KDF to protect against that a fast
    hash doesn't already cover -- and login-path bcrypt-style hashing would
    add needless latency to every authenticated request."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
