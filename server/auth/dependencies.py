"""FastAPI dependency helpers: bearer-token extraction, current-user
resolution, and role-based access guards (design doc §7.1, RBAC in §2 T2.2).

Uses a simple module-level singleton for the AuthService instance rather
than a full DI container: server/main.py calls set_auth_service() once at
startup (same spirit as its existing module-level `db`/`rooms` singletons),
and route/dependency functions pull it via get_auth_service().
"""

import time

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from server.auth.errors import AuthHTTPError
from server.auth.service import AuthService, SessionRevokedError

_bearer_scheme = HTTPBearer(auto_error=False)

_service: AuthService | None = None
_oauth2_providers: dict = {}
_oauth2_http_client = None


def set_auth_service(service: AuthService) -> None:
    global _service
    _service = service


def get_auth_service() -> AuthService:
    if _service is None:
        raise RuntimeError("AuthService has not been initialized; call set_auth_service() at startup")
    return _service


def set_oauth2_providers(providers: dict) -> None:
    """`providers` maps provider name -> OAuth2ProviderSettings (design doc
    §4.3/§4.4). Only providers with real credentials configured are present."""
    global _oauth2_providers
    _oauth2_providers = providers


def get_oauth2_providers() -> dict:
    return _oauth2_providers


def set_oauth2_http_client(client) -> None:
    global _oauth2_http_client
    _oauth2_http_client = client


def get_oauth2_http_client():
    if _oauth2_http_client is None:
        raise RuntimeError("OAuth2 HTTP client has not been initialized; call set_oauth2_http_client() at startup")
    return _oauth2_http_client


def get_client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    service: AuthService = Depends(get_auth_service),
) -> dict:
    if credentials is None:
        raise AuthHTTPError(401, "TOKEN_MISSING", "An access token is required.")
    try:
        return await service.get_current_user(access_token=credentials.credentials, now_ms=time.time() * 1000)
    except SessionRevokedError as exc:
        raise AuthHTTPError(401, "TOKEN_INVALID", str(exc)) from exc


def require_role(*roles: str):
    """Dependency factory: the resulting dependency allows a user whose
    `role` is one of `roles`, OR who has the `isAdmin` flag set (an admin
    can always reach an educator/moderator-gated route, matching the
    'admin can do anything' expectation from the design doc's persona
    descriptions)."""

    async def _dependency(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles and not user.get("isAdmin"):
            raise AuthHTTPError(403, "FORBIDDEN", "You do not have permission to perform this action.")
        return user

    return _dependency
