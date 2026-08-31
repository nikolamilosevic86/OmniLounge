"""/api/auth/oauth2/* HTTP endpoints (design doc §7.1.6, §7.1.7).

PKCE `state` and `code_verifier` are generated and stored by the frontend
across the redirect (design doc §19.6's token-storage notes apply to the
verifier too), so these routes are a stateless relay: `authorize` forwards
the challenge to the provider, and `callback` forwards the verifier back
for the provider itself to check consistency during code exchange.
"""

import time

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from server.auth.dependencies import get_auth_service, get_client_ip, get_oauth2_http_client, get_oauth2_providers
from server.auth.errors import AuthHTTPError
from server.auth.oauth2 import (
    OAuth2Error,
    OAuth2ProviderUnavailableError,
    build_authorization_url,
    resolve_provider_identity,
)
from server.auth.service import (
    AuthService,
    OAuth2GroupNotAllowedError,
    OAuth2ProfileMissingEmailError,
    RateLimitedError,
    SessionRevokedError,
)

router = APIRouter(prefix="/api/auth/oauth2", tags=["auth"])


class OAuth2CallbackBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=2048)
    code_verifier: str = Field(alias="codeVerifier", min_length=1, max_length=256)


@router.get("/authorize/{provider}")
async def oauth2_authorize(
    provider: str,
    state: str = Query(min_length=1, max_length=2048),
    code_challenge: str = Query(min_length=1, max_length=256),
    providers: dict = Depends(get_oauth2_providers),
):
    settings = providers.get(provider)
    if settings is None:
        raise AuthHTTPError(404, "NOT_FOUND", f"Unknown or disabled OAuth2 provider: {provider!r}")
    url = build_authorization_url(settings, state=state, code_challenge=code_challenge)
    return RedirectResponse(url, status_code=302)


@router.post("/callback/{provider}")
async def oauth2_callback(
    provider: str, body: OAuth2CallbackBody, client_ip: str | None = Depends(get_client_ip),
    providers: dict = Depends(get_oauth2_providers), service: AuthService = Depends(get_auth_service),
    http_client: httpx.AsyncClient = Depends(get_oauth2_http_client),
):
    settings = providers.get(provider)
    if settings is None:
        raise AuthHTTPError(404, "NOT_FOUND", f"Unknown or disabled OAuth2 provider: {provider!r}")

    try:
        identity = await resolve_provider_identity(
            settings, code=body.code, code_verifier=body.code_verifier, http_client=http_client,
        )
    except OAuth2ProviderUnavailableError as exc:
        raise AuthHTTPError(503, "PROVIDER_UNAVAILABLE", "Could not reach the identity provider. Please try again.") from exc
    except OAuth2Error as exc:
        raise AuthHTTPError(401, "INVALID_CREDENTIALS", "Provider authentication failed.") from exc

    try:
        session = await service.oauth2_login(
            provider_name=provider, identity=identity, now_ms=time.time() * 1000, ip=client_ip,
            allowed_groups=settings.allowed_groups,
        )
    except OAuth2ProfileMissingEmailError as exc:
        raise AuthHTTPError(
            400, "VALIDATION_ERROR",
            "The identity provider did not share an email address for this account.",
        ) from exc
    except OAuth2GroupNotAllowedError as exc:
        raise AuthHTTPError(403, "FORBIDDEN", "Your account is not authorized for this application.") from exc
    except SessionRevokedError as exc:
        raise AuthHTTPError(401, "INVALID_CREDENTIALS", "This account is disabled.") from exc
    except RateLimitedError as exc:
        raise AuthHTTPError(429, "RATE_LIMITED", str(exc)) from exc

    user = session["user"]
    return {
        "access_token": session["access_token"],
        "refresh_token": session["refresh_token"],
        "expires_in": session["expires_in"],
        "is_new_user": session["is_new_user"],
        "user": {
            "id": user["id"], "email": user["email"], "display_name": user["displayName"],
            "avatar_id": None, "role": user["role"],
        },
    }
