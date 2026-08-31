"""/api/user/* self-service HTTP endpoints (design doc §7.3): profile,
password change, and session listing/revocation.
"""

import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from server.auth.dependencies import get_auth_service, get_current_user
from server.auth.errors import AuthHTTPError
from server.auth.service import AuthService, InvalidCredentialsError, WeakPasswordError

router = APIRouter(prefix="/api/user", tags=["user"])


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str | None = Field(default=None, alias="displayName", min_length=1, max_length=255)
    bio: str | None = Field(default=None, max_length=2000)
    preferred_topics: list[str] | None = Field(default=None, alias="preferredTopics")


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    current_password: str = Field(alias="currentPassword", min_length=1, max_length=200)
    new_password: str = Field(alias="newPassword", min_length=1, max_length=200)


def _profile_view(user: dict) -> dict:
    return {
        "id": user["id"], "email": user["email"], "display_name": user["displayName"],
        "role": user.get("role"), "bio": user.get("bio"), "preferred_topics": user.get("preferredTopics"),
        "created_at": user.get("createdAt"),
    }


@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    return _profile_view(user)


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdateRequest, user: dict = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    updated = await service.update_profile(
        user_id=user["id"], display_name=body.display_name, bio=body.bio,
        preferred_topics=body.preferred_topics,
    )
    return _profile_view(updated)


@router.post("/password-change")
async def change_password(
    body: PasswordChangeRequest, user: dict = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    try:
        await service.change_password(
            user_id=user["id"], current_password=body.current_password, new_password=body.new_password,
            now_ms=time.time() * 1000,
        )
    except WeakPasswordError as exc:
        raise AuthHTTPError(400, "WEAK_PASSWORD", "; ".join(exc.errors), {"errors": exc.errors}) from exc
    except InvalidCredentialsError as exc:
        raise AuthHTTPError(401, "INVALID_CREDENTIALS", str(exc)) from exc
    return {"message": "Password changed successfully"}


@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user), service: AuthService = Depends(get_auth_service)):
    sessions = await service.list_sessions(user_id=user["id"])
    return {
        "sessions": [
            {
                "id": s["id"], "device_name": s.get("device_name"), "ip_address": s.get("ip_address"),
                "last_activity_at": s.get("last_activity_at"), "created_at": s.get("created_at"),
            }
            for s in sessions
        ],
    }


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: str, user: dict = Depends(get_current_user), service: AuthService = Depends(get_auth_service),
):
    revoked = await service.revoke_session(user_id=user["id"], session_id=session_id)
    if not revoked:
        raise AuthHTTPError(404, "NOT_FOUND", "No session with that id.")
    return {"message": "Session revoked"}
