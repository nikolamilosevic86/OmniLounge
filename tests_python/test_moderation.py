import pytest

from server.game.moderation import (
    ROLE_CO_EDITOR,
    ROLE_MODERATOR,
    ROLE_OWNER,
    ROLE_PARTICIPANT,
    ModerationState,
    contains_external_link,
)


class TestRoles:
    def setup_method(self):
        self.mod = ModerationState(owner_id="alice")

    def test_owner_role_is_implicit_for_owner_id(self):
        assert self.mod.get_role("alice") == ROLE_OWNER

    def test_unknown_user_defaults_to_participant(self):
        assert self.mod.get_role("bob") == ROLE_PARTICIPANT

    def test_owner_can_assign_co_editor_role(self):
        self.mod.assign_role("bob", ROLE_CO_EDITOR, actor_id="alice")
        assert self.mod.get_role("bob") == ROLE_CO_EDITOR

    def test_owner_can_assign_moderator_role(self):
        self.mod.assign_role("bob", ROLE_MODERATOR, actor_id="alice")
        assert self.mod.get_role("bob") == ROLE_MODERATOR

    def test_owner_can_reassign_role_to_participant(self):
        self.mod.assign_role("bob", ROLE_CO_EDITOR, actor_id="alice")
        self.mod.assign_role("bob", ROLE_PARTICIPANT, actor_id="alice")
        assert self.mod.get_role("bob") == ROLE_PARTICIPANT

    def test_non_owner_cannot_assign_roles(self):
        with pytest.raises(PermissionError):
            self.mod.assign_role("carol", ROLE_CO_EDITOR, actor_id="bob")

    def test_cannot_reassign_owner_role(self):
        with pytest.raises(ValueError):
            self.mod.assign_role("alice", ROLE_PARTICIPANT, actor_id="alice")

    def test_invalid_role_name_rejected(self):
        with pytest.raises(ValueError):
            self.mod.assign_role("bob", "supreme_leader", actor_id="alice")


class TestPermissions:
    def setup_method(self):
        self.mod = ModerationState(owner_id="alice")

    def test_owner_has_all_permissions(self):
        for permission in ("layout_edit", "content_edit", "npc_story_edit", "publish", "moderate", "ai_settings"):
            assert self.mod.has_permission("alice", permission)

    def test_co_editor_has_edit_permissions_but_not_moderate_or_ai_settings(self):
        self.mod.assign_role("bob", ROLE_CO_EDITOR, actor_id="alice")
        assert self.mod.has_permission("bob", "layout_edit")
        assert self.mod.has_permission("bob", "content_edit")
        assert self.mod.has_permission("bob", "npc_story_edit")
        assert not self.mod.has_permission("bob", "moderate")
        assert not self.mod.has_permission("bob", "ai_settings")

    def test_moderator_has_moderate_but_not_edit_permissions(self):
        self.mod.assign_role("bob", ROLE_MODERATOR, actor_id="alice")
        assert self.mod.has_permission("bob", "moderate")
        assert not self.mod.has_permission("bob", "layout_edit")

    def test_participant_has_no_special_permissions(self):
        assert not self.mod.has_permission("carol", "layout_edit")
        assert not self.mod.has_permission("carol", "moderate")

    def test_require_permission_raises_when_missing(self):
        with pytest.raises(PermissionError):
            self.mod.require_permission("carol", "moderate")

    def test_require_permission_passes_silently_when_present(self):
        self.mod.require_permission("alice", "moderate")


class TestMuting:
    def setup_method(self):
        self.mod = ModerationState(owner_id="alice")
        self.mod.assign_role("mod1", ROLE_MODERATOR, actor_id="alice")

    def test_moderator_can_mute_and_unmute_a_user(self):
        self.mod.mute("carol", actor_id="mod1")
        assert self.mod.is_muted("carol") is True
        self.mod.unmute("carol", actor_id="mod1")
        assert self.mod.is_muted("carol") is False

    def test_participant_cannot_mute(self):
        with pytest.raises(PermissionError):
            self.mod.mute("carol", actor_id="dave")

    def test_unmuted_user_by_default(self):
        assert self.mod.is_muted("someone") is False


class TestKickAndBan:
    def setup_method(self):
        self.mod = ModerationState(owner_id="alice")
        self.mod.assign_role("mod1", ROLE_MODERATOR, actor_id="alice")

    def test_moderator_can_kick_a_participant(self):
        self.mod.kick("carol", actor_id="mod1")

    def test_cannot_kick_the_owner(self):
        with pytest.raises(PermissionError):
            self.mod.kick("alice", actor_id="mod1")

    def test_participant_cannot_kick(self):
        with pytest.raises(PermissionError):
            self.mod.kick("carol", actor_id="dave")

    def test_moderator_can_ban_and_unban_a_user(self):
        self.mod.ban("carol", actor_id="mod1")
        assert self.mod.is_banned("carol") is True
        self.mod.unban("carol", actor_id="mod1")
        assert self.mod.is_banned("carol") is False

    def test_cannot_ban_the_owner(self):
        with pytest.raises(PermissionError):
            self.mod.ban("alice", actor_id="mod1")

    def test_not_banned_by_default(self):
        assert self.mod.is_banned("someone") is False


class TestContentReporting:
    def setup_method(self):
        self.mod = ModerationState(owner_id="alice")
        self.mod.assign_role("mod1", ROLE_MODERATOR, actor_id="alice")

    def test_any_user_can_report_content(self):
        report = self.mod.report_content("carol", "chat_message", "msg-1", "spam")
        assert report["reporterId"] == "carol"
        assert report["targetType"] == "chat_message"
        assert report["targetId"] == "msg-1"
        assert report["reason"] == "spam"
        assert "createdAtMs" in report

    def test_moderator_can_list_reports(self):
        self.mod.report_content("carol", "chat_message", "msg-1", "spam")
        reports = self.mod.list_reports(actor_id="mod1")
        assert len(reports) == 1

    def test_non_moderator_cannot_list_reports(self):
        self.mod.report_content("carol", "chat_message", "msg-1", "spam")
        with pytest.raises(PermissionError):
            self.mod.list_reports(actor_id="dave")


class TestAuditLog:
    def setup_method(self):
        self.mod = ModerationState(owner_id="alice")

    def test_role_assignment_is_logged(self):
        self.mod.assign_role("bob", ROLE_CO_EDITOR, actor_id="alice")
        log = self.mod.list_audit_log(actor_id="alice")
        assert any(entry["action"] == "assign_role" and entry["targetId"] == "bob" for entry in log)

    def test_moderation_actions_are_logged(self):
        self.mod.assign_role("mod1", ROLE_MODERATOR, actor_id="alice")
        self.mod.mute("carol", actor_id="mod1")
        self.mod.kick("dave", actor_id="mod1")
        self.mod.ban("erin", actor_id="mod1")
        log = self.mod.list_audit_log(actor_id="alice")
        actions = {entry["action"] for entry in log}
        assert {"mute", "kick", "ban"}.issubset(actions)

    def test_audit_log_requires_moderate_permission(self):
        with pytest.raises(PermissionError):
            self.mod.list_audit_log(actor_id="dave")

    def test_audit_log_entries_have_actor_and_timestamp(self):
        self.mod.assign_role("bob", ROLE_CO_EDITOR, actor_id="alice")
        entry = self.mod.list_audit_log(actor_id="alice")[0]
        assert entry["actorId"] == "alice"
        assert "atMs" in entry


class TestExternalContentPolicy:
    def setup_method(self):
        self.mod = ModerationState(owner_id="alice")

    def test_external_links_allowed_by_default(self):
        assert self.mod.are_external_links_allowed() is True

    def test_owner_can_restrict_external_links(self):
        self.mod.set_external_links_allowed(False, actor_id="alice")
        assert self.mod.are_external_links_allowed() is False

    def test_non_owner_cannot_change_external_link_policy(self):
        with pytest.raises(PermissionError):
            self.mod.set_external_links_allowed(False, actor_id="bob")

    def test_changing_external_link_policy_is_audit_logged(self):
        self.mod.set_external_links_allowed(False, actor_id="alice")
        log = self.mod.list_audit_log(actor_id="alice")
        assert any(entry["action"] == "set_external_links_policy" for entry in log)


class TestContainsExternalLink:
    def test_detects_http_url(self):
        assert contains_external_link("check out http://example.com") is True

    def test_detects_https_url(self):
        assert contains_external_link("visit https://example.com/page") is True

    def test_detects_bare_www_domain(self):
        assert contains_external_link("go to www.example.com now") is True

    def test_plain_text_has_no_link(self):
        assert contains_external_link("hello, how are you today?") is False

    def test_empty_text_has_no_link(self):
        assert contains_external_link("") is False
