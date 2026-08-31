"""/api/admin/* HTTP endpoints (design doc §7.2). Every route is gated by
`require_role("admin")`, so only a user with `role == "admin"` or the
`isAdmin` flag set can reach any of them.
"""

import csv
import io
import time

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from server.auth.dependencies import get_auth_service, require_role
from server.auth.errors import AuthHTTPError
from server.auth.service import (
    ALLOWED_ROLES,
    AuthService,
    BulkImportTooLargeError,
    DuplicateEmailError,
    DuplicateUsernameError,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# A raw upload larger than this is rejected outright rather than parsed --
# an admin-only endpoint is still a request an attacker who steals/forges an
# admin session could hit, and CSV parsing of an arbitrarily large file is
# needless memory/CPU exposure.
_MAX_IMPORT_FILE_BYTES = 2_000_000


def _user_summary(user: dict) -> dict:
    return {
        "id": user["id"], "email": user["email"], "username": user["username"],
        "display_name": user["displayName"], "role": user["role"], "is_active": user["isActive"],
        "is_admin": user["isAdmin"], "email_verified": user["emailVerified"],
        "last_login_at": user["lastLoginAt"], "created_at": user["createdAt"],
    }


class AdminCreateUserRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    display_name: str = Field(alias="displayName", min_length=1, max_length=255)
    username: str | None = Field(default=None, min_length=3, max_length=100)
    role: str = "learner"


class AdminUpdateUserRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str | None = Field(default=None, alias="displayName", min_length=1, max_length=255)
    role: str | None = None
    is_active: bool | None = Field(default=None, alias="isActive")


@router.post("/users", status_code=201)
async def admin_create_user(
    body: AdminCreateUserRequest, admin: dict = Depends(require_role("admin")),
    service: AuthService = Depends(get_auth_service),
):
    if body.role not in ALLOWED_ROLES:
        raise AuthHTTPError(400, "VALIDATION_ERROR", f"role must be one of {ALLOWED_ROLES}")
    try:
        user, temp_password = await service.admin_create_user(
            email=body.email, display_name=body.display_name, username=body.username,
            role=body.role, created_by=admin.get("id"),
        )
    except DuplicateEmailError as exc:
        raise AuthHTTPError(409, "EMAIL_TAKEN", "This email is already registered.") from exc
    except DuplicateUsernameError as exc:
        raise AuthHTTPError(409, "USERNAME_TAKEN", "This username is already taken.") from exc
    return {
        "id": user["id"], "email": user["email"], "username": user["username"],
        "display_name": user["displayName"], "temporary_password": temp_password,
        "message": "User created. Share the temporary password with them securely.",
    }


@router.post("/users/import")
async def bulk_import_users(
    file: UploadFile = File(...), admin: dict = Depends(require_role("admin")),
    service: AuthService = Depends(get_auth_service),
):
    raw = await file.read()
    if len(raw) > _MAX_IMPORT_FILE_BYTES:
        raise AuthHTTPError(400, "VALIDATION_ERROR", "CSV file is too large (max 2MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AuthHTTPError(400, "VALIDATION_ERROR", "CSV file must be UTF-8 encoded.") from exc

    rows = list(csv.DictReader(io.StringIO(text)))
    try:
        return await service.admin_bulk_import_users(rows=rows, created_by=admin.get("id"))
    except BulkImportTooLargeError as exc:
        raise AuthHTTPError(400, "VALIDATION_ERROR", str(exc)) from exc


@router.get("/users", dependencies=[Depends(require_role("admin"))])
async def list_users(
    role: str | None = None, is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    service: AuthService = Depends(get_auth_service),
):
    users, total = await service.list_users(role=role, is_active=is_active, limit=limit, offset=offset)
    return {"users": [_user_summary(u) for u in users], "total": total, "limit": limit, "offset": offset}


@router.get("/users/{user_id}", dependencies=[Depends(require_role("admin"))])
async def get_user(user_id: str, service: AuthService = Depends(get_auth_service)):
    user = await service.get_user(user_id)
    if user is None:
        raise AuthHTTPError(404, "NOT_FOUND", "No user with that id.")
    return _user_summary(user)


@router.patch("/users/{user_id}", dependencies=[Depends(require_role("admin"))])
async def update_user(
    user_id: str, body: AdminUpdateUserRequest, service: AuthService = Depends(get_auth_service),
):
    if body.role is not None and body.role not in ALLOWED_ROLES:
        raise AuthHTTPError(400, "VALIDATION_ERROR", f"role must be one of {ALLOWED_ROLES}")
    user = await service.admin_update_user(
        user_id=user_id, display_name=body.display_name, role=body.role, is_active=body.is_active,
    )
    if user is None:
        raise AuthHTTPError(404, "NOT_FOUND", "No user with that id.")
    return _user_summary(user)


@router.post("/users/{user_id}/reset-password", dependencies=[Depends(require_role("admin"))])
async def reset_password(user_id: str, service: AuthService = Depends(get_auth_service)):
    if await service.get_user(user_id) is None:
        raise AuthHTTPError(404, "NOT_FOUND", "No user with that id.")
    temp_password = await service.admin_reset_password(user_id=user_id, now_ms=time.time() * 1000)
    return {
        "temporary_password": temp_password,
        "message": "Password reset. User will be required to change it on next login.",
    }


@router.post("/users/{user_id}/disable", dependencies=[Depends(require_role("admin"))])
async def disable_user(user_id: str, service: AuthService = Depends(get_auth_service)):
    if await service.get_user(user_id) is None:
        raise AuthHTTPError(404, "NOT_FOUND", "No user with that id.")
    await service.admin_disable_user(user_id=user_id)
    return {"message": "User account disabled"}


@router.post("/users/{user_id}/enable", dependencies=[Depends(require_role("admin"))])
async def enable_user(user_id: str, service: AuthService = Depends(get_auth_service)):
    if await service.get_user(user_id) is None:
        raise AuthHTTPError(404, "NOT_FOUND", "No user with that id.")
    await service.admin_enable_user(user_id=user_id)
    return {"message": "User account enabled"}


@router.post("/users/{user_id}/unlock", dependencies=[Depends(require_role("admin"))])
async def unlock_user(user_id: str, service: AuthService = Depends(get_auth_service)):
    if await service.get_user(user_id) is None:
        raise AuthHTTPError(404, "NOT_FOUND", "No user with that id.")
    await service.admin_unlock_user(user_id=user_id)
    return {"message": "User account unlocked. Failed attempt counter reset."}


@router.delete("/users/{user_id}", status_code=204, dependencies=[Depends(require_role("admin"))])
async def delete_user(user_id: str, service: AuthService = Depends(get_auth_service)):
    if not await service.admin_delete_user(user_id=user_id):
        raise AuthHTTPError(404, "NOT_FOUND", "No user with that id.")
    return None


@router.get("/audit-log", dependencies=[Depends(require_role("admin"))])
async def get_audit_log(
    user_id: str | None = None, event_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    service: AuthService = Depends(get_auth_service),
):
    events = await service.list_audit_events(user_id=user_id, event_type=event_type, limit=limit)
    return {"events": events, "total": len(events)}
