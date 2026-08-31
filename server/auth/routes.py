"""/api/auth/* HTTP endpoints (design doc §7.1).

Request/response field names use camelCase over the wire (e.g. `displayName`,
`emailOrUsername`), matching this codebase's existing JSON convention (see
e.g. `KnowledgeDocumentModel` in server/game/story.py) rather than the
design doc's illustrative snake_case examples, which were written
independently of this codebase.
"""

import time

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from server.auth.config import auth_config as default_auth_config
from server.auth.dependencies import get_auth_service, get_client_ip, get_current_user, get_oauth2_providers
from server.auth.errors import AuthHTTPError
from server.auth.service import (
    AccountLockedError,
    AuthService,
    DuplicateEmailError,
    DuplicateUsernameError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidResetTokenError,
    RateLimitedError,
    RegistrationDisabledError,
    SessionRevokedError,
    WeakPasswordError,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _raise_for_service_error(exc: Exception) -> None:
    if isinstance(exc, WeakPasswordError):
        raise AuthHTTPError(400, "WEAK_PASSWORD", "; ".join(exc.errors), {"errors": exc.errors}) from exc
    if isinstance(exc, DuplicateEmailError):
        raise AuthHTTPError(409, "EMAIL_TAKEN", "This email is already registered.") from exc
    if isinstance(exc, DuplicateUsernameError):
        raise AuthHTTPError(409, "USERNAME_TAKEN", "This username is already taken.") from exc
    if isinstance(exc, RegistrationDisabledError):
        raise AuthHTTPError(403, "REGISTRATION_DISABLED", "Registration is currently disabled.") from exc
    if isinstance(exc, AccountLockedError):
        raise AuthHTTPError(403, "ACCOUNT_LOCKED", "Too many failed attempts. Try again later.") from exc
    if isinstance(exc, EmailNotVerifiedError):
        raise AuthHTTPError(403, "EMAIL_NOT_VERIFIED", str(exc)) from exc
    if isinstance(exc, InvalidCredentialsError):
        message = str(exc) or "The provided credentials are incorrect."
        raise AuthHTTPError(401, "INVALID_CREDENTIALS", message) from exc
    if isinstance(exc, InvalidResetTokenError):
        raise AuthHTTPError(400, "TOKEN_INVALID", str(exc)) from exc
    if isinstance(exc, SessionRevokedError):
        raise AuthHTTPError(401, "TOKEN_INVALID", str(exc)) from exc
    if isinstance(exc, RateLimitedError):
        raise AuthHTTPError(429, "RATE_LIMITED", str(exc)) from exc
    raise


class RegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    display_name: str = Field(alias="displayName", min_length=1, max_length=255)
    username: str | None = Field(default=None, min_length=3, max_length=100)


class LoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email_or_username: str = Field(alias="emailOrUsername", min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    refresh_token: str = Field(alias="refreshToken", min_length=1)


class PasswordResetRequestBody(BaseModel):
    email: EmailStr


class PasswordResetConfirmBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str = Field(min_length=1)
    new_password: str = Field(alias="newPassword", min_length=1, max_length=200)


class VerifyEmailBody(BaseModel):
    token: str = Field(min_length=1)


@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest, client_ip: str | None = Depends(get_client_ip),
    service: AuthService = Depends(get_auth_service),
):
    try:
        user = await service.register(
            email=body.email, password=body.password, display_name=body.display_name,
            username=body.username, now_ms=time.time() * 1000, ip=client_ip,
        )
    except Exception as exc:  # noqa: BLE001 -- translated to a typed HTTP error below
        _raise_for_service_error(exc)
        raise
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["displayName"],
        "email_verified": user["emailVerified"],
        "requires_avatar": True,
        "message": "Registration successful.",
    }


@router.post("/login")
async def login(
    body: LoginRequest, client_ip: str | None = Depends(get_client_ip),
    service: AuthService = Depends(get_auth_service),
):
    try:
        result = await service.login(
            email_or_username=body.email_or_username, password=body.password,
            now_ms=time.time() * 1000, ip=client_ip,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_for_service_error(exc)
        raise
    user = result["user"]
    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "expires_in": result["expires_in"],
        "user": {
            "id": user["id"], "email": user["email"], "display_name": user["displayName"],
            "avatar_id": None, "role": user["role"],
        },
    }


@router.post("/refresh")
async def refresh(body: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    try:
        result = await service.refresh(refresh_token=body.refresh_token, now_ms=time.time() * 1000)
    except Exception as exc:  # noqa: BLE001
        _raise_for_service_error(exc)
        raise
    return result


@router.post("/logout")
async def logout(
    authorization: str | None = Header(default=None), service: AuthService = Depends(get_auth_service),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthHTTPError(401, "TOKEN_MISSING", "An access token is required.")
    token = authorization.split(" ", 1)[1]
    try:
        await service.logout(access_token=token, now_ms=time.time() * 1000)
    except Exception as exc:  # noqa: BLE001
        _raise_for_service_error(exc)
        raise
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {
        "id": user["id"], "email": user["email"], "display_name": user["displayName"],
        "role": user["role"], "avatar_id": None,
        "requires_password_change": user["requiresPasswordChange"],
        "requires_avatar": False,
        "auth_provider": "local",
    }


@router.get("/providers")
async def get_providers(
    service: AuthService = Depends(get_auth_service), oauth2_providers: dict = Depends(get_oauth2_providers),
):
    config = getattr(service, "_config", default_auth_config)
    return {
        "local_registration_enabled": config.enable_local_registration,
        "local_login_enabled": config.enable_local_login,
        "oauth2_providers": [
            {
                "name": provider.name, "label": provider.label,
                "authorize_url": f"/api/auth/oauth2/authorize/{provider.name}",
            }
            for provider in oauth2_providers.values()
        ],
    }


@router.post("/password-reset/request")
async def request_password_reset(
    body: PasswordResetRequestBody, service: AuthService = Depends(get_auth_service),
):
    # Always returns the same message whether or not the email exists, so a
    # caller can't enumerate registered accounts through this endpoint.
    await service.request_password_reset(email=body.email, now_ms=time.time() * 1000)
    return {"message": "If an account with this email exists, a password reset link has been sent."}


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    body: PasswordResetConfirmBody, service: AuthService = Depends(get_auth_service),
):
    try:
        await service.confirm_password_reset(
            token=body.token, new_password=body.new_password, now_ms=time.time() * 1000,
        )
    except Exception as exc:  # noqa: BLE001
        _raise_for_service_error(exc)
        raise
    return {"message": "Password reset successful. Please log in with your new password."}


@router.post("/verify-email")
async def verify_email(body: VerifyEmailBody, service: AuthService = Depends(get_auth_service)):
    try:
        await service.confirm_email_verification(token=body.token)
    except Exception as exc:  # noqa: BLE001
        _raise_for_service_error(exc)
        raise
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification(
    user: dict = Depends(get_current_user), service: AuthService = Depends(get_auth_service),
):
    if user["emailVerified"]:
        raise AuthHTTPError(400, "VALIDATION_ERROR", "This email is already verified.")
    await service.request_email_verification(user_id=user["id"], now_ms=time.time() * 1000)
    return {"message": "Verification email resent. Please check your inbox."}
