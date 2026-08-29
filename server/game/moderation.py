"""Phase I: room roles, permissions, and moderation tools.

Feature design reference: "Collaboration, Roles, and Moderation" section.
Roles: owner (implicit room creator), co_editor, moderator, participant
(default). Owner assigns roles; moderators/owner can mute, kick, ban, and
review reported content. Every admin/moderation action is appended to an
in-memory audit log.
"""

import re
import time
from typing import Any

_EXTERNAL_LINK_PATTERN = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)


def contains_external_link(text: str) -> bool:
    """Return True if `text` contains what looks like an external URL."""
    return bool(_EXTERNAL_LINK_PATTERN.search(text or ""))


ROLE_OWNER = "owner"
ROLE_CO_EDITOR = "co_editor"
ROLE_MODERATOR = "moderator"
ROLE_PARTICIPANT = "participant"

ASSIGNABLE_ROLES = {ROLE_CO_EDITOR, ROLE_MODERATOR, ROLE_PARTICIPANT}

# Permission matrix, see feature design "Permissions" list.
_ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_OWNER: {
        "layout_edit", "content_edit", "npc_story_edit", "publish", "moderate", "ai_settings",
    },
    ROLE_CO_EDITOR: {"layout_edit", "content_edit", "npc_story_edit"},
    ROLE_MODERATOR: {"moderate"},
    ROLE_PARTICIPANT: set(),
}


class ModerationState:
    """Per-room role assignments, moderation actions, and audit log."""

    def __init__(self, owner_id: str) -> None:
        self._owner_id = owner_id
        self._roles: dict[str, str] = {}
        self._muted: set[str] = set()
        self._banned: set[str] = set()
        self._reports: list[dict[str, Any]] = []
        self._audit_log: list[dict[str, Any]] = []
        self._external_links_allowed = True

    # ─── Roles ──────────────────────────────────────────────────────────

    def get_role(self, user_id: str) -> str:
        if user_id == self._owner_id:
            return ROLE_OWNER
        return self._roles.get(user_id, ROLE_PARTICIPANT)

    def assign_role(self, user_id: str, role: str, actor_id: str) -> None:
        if actor_id != self._owner_id:
            raise PermissionError("only the room owner can assign roles")
        if user_id == self._owner_id:
            raise ValueError("cannot change the owner's role")
        if role not in ASSIGNABLE_ROLES:
            raise ValueError(f"invalid role: {role!r}")
        self._roles[user_id] = role
        self._log(actor_id, "assign_role", user_id, {"role": role})

    def reassign_owner(self, new_owner_id: str) -> None:
        """Transfer room ownership to `new_owner_id`. Used when a room
        creator's connection identity changes (e.g. reconnect/refresh) and
        they re-prove ownership via a host-reclaim token; the token check
        itself is the authorization, so no actor/permission check is done
        here."""
        previous_owner_id = self._owner_id
        self._owner_id = new_owner_id
        self._roles.pop(new_owner_id, None)
        self._log(previous_owner_id, "reassign_owner", new_owner_id)

    def has_permission(self, user_id: str, permission: str) -> bool:
        role = self.get_role(user_id)
        return permission in _ROLE_PERMISSIONS.get(role, set())

    def require_permission(self, user_id: str, permission: str) -> None:
        if not self.has_permission(user_id, permission):
            raise PermissionError(f"user lacks required permission: {permission!r}")

    # ─── Moderation actions ─────────────────────────────────────────────

    def mute(self, target_id: str, actor_id: str) -> None:
        self.require_permission(actor_id, "moderate")
        # Same owner guard `kick`/`ban` already have -- without it a
        # moderator the owner appointed can silence the owner in their own
        # room (`chat_send` enforces `is_muted`).
        if target_id == self._owner_id:
            raise PermissionError("cannot mute the room owner")
        self._muted.add(target_id)
        self._log(actor_id, "mute", target_id)

    def unmute(self, target_id: str, actor_id: str) -> None:
        self.require_permission(actor_id, "moderate")
        self._muted.discard(target_id)
        self._log(actor_id, "unmute", target_id)

    def is_muted(self, user_id: str) -> bool:
        return user_id in self._muted

    def kick(self, target_id: str, actor_id: str) -> None:
        self.require_permission(actor_id, "moderate")
        if target_id == self._owner_id:
            raise PermissionError("cannot kick the room owner")
        self._log(actor_id, "kick", target_id)

    def ban(self, target_id: str, actor_id: str) -> None:
        self.require_permission(actor_id, "moderate")
        if target_id == self._owner_id:
            raise PermissionError("cannot ban the room owner")
        self._banned.add(target_id)
        self._log(actor_id, "ban", target_id)

    def unban(self, target_id: str, actor_id: str) -> None:
        self.require_permission(actor_id, "moderate")
        self._banned.discard(target_id)
        self._log(actor_id, "unban", target_id)

    def is_banned(self, user_id: str) -> bool:
        return user_id in self._banned

    # ─── Content reporting ──────────────────────────────────────────────

    def report_content(
        self, reporter_id: str, target_type: str, target_id: str, reason: str
    ) -> dict[str, Any]:
        report = {
            "reporterId": reporter_id,
            "targetType": target_type,
            "targetId": target_id,
            "reason": reason,
            "createdAtMs": int(time.time() * 1000),
        }
        self._reports.append(report)
        self._log(reporter_id, "report_content", target_id, {"targetType": target_type, "reason": reason})
        return dict(report)

    def list_reports(self, actor_id: str) -> list[dict[str, Any]]:
        self.require_permission(actor_id, "moderate")
        return [dict(report) for report in self._reports]

    # ─── External content policy ────────────────────────────────────────

    def are_external_links_allowed(self) -> bool:
        return self._external_links_allowed

    def set_external_links_allowed(self, allowed: bool, actor_id: str) -> None:
        if actor_id != self._owner_id:
            raise PermissionError("only the room owner can change the external link policy")
        self._external_links_allowed = bool(allowed)
        self._log(actor_id, "set_external_links_policy", None, {"allowed": bool(allowed)})

    # ─── Audit log ──────────────────────────────────────────────────────

    def _log(
        self, actor_id: str, action: str, target_id: str | None = None, details: dict[str, Any] | None = None
    ) -> None:
        self._audit_log.append({
            "actorId": actor_id,
            "action": action,
            "targetId": target_id,
            "details": details or {},
            "atMs": int(time.time() * 1000),
        })

    def list_audit_log(self, actor_id: str) -> list[dict[str, Any]]:
        self.require_permission(actor_id, "moderate")
        return [dict(entry) for entry in self._audit_log]
