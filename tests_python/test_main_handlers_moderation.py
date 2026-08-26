import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar
from server.game.moderation import ROLE_MODERATOR


class FakeSio:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data=None, room=None, skip_sid=None):
        self.emitted.append((event, data, room))

    async def enter_room(self, sid, room):
        return None

    async def leave_room(self, sid, room):
        return None


@pytest.fixture(autouse=True)
def isolate_registry(monkeypatch):
    """Give each test a clean rooms registry and a fake sio so no real
    network/db access happens, and tests don't leak player state."""
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)

    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    async def fake_save_message(message, room_id="lobby"):
        return None

    monkeypatch.setattr(main_module.db, "save_message", fake_save_message)

    async def fake_get_recent_messages(room_id="lobby", limit=50):
        return []

    monkeypatch.setattr(main_module.db, "get_recent_messages", fake_get_recent_messages)
    return fresh_rooms, fake_sio


async def _make_room_with_host(rooms, host_id="host1", name="Edu Room"):
    room = rooms.create_room(host_id=host_id, name=name)
    avatar = create_default_avatar("Host")
    rooms.join_room(host_id, avatar, room["id"])
    return room


async def _join_room(rooms, player_id, room_id, username="Guest"):
    avatar = create_default_avatar(username)
    rooms.join_room(player_id, avatar, room_id)


class TestRoleAssignmentHandler:
    async def test_owner_can_assign_moderator_role(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "bob", room["id"])

        result = await main_module.room_role_assign("host1", {"targetId": "bob", "role": "moderator"})

        assert result["role"] == "moderator"
        moderation = rooms.get_moderation(room["id"])
        assert moderation.get_role("bob") == "moderator"

    async def test_non_owner_cannot_assign_roles(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "bob", room["id"])
        await _join_room(rooms, "carol", room["id"])

        await main_module.room_role_assign("bob", {"targetId": "carol", "role": "moderator"})

        error_events = [e for e in fake_sio.emitted if e[0] == "error"]
        assert error_events
        assert rooms.get_moderation(room["id"]).get_role("carol") == "participant"

    async def test_room_state_payload_reflects_current_roles_and_muted_status(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "bob", room["id"])
        await _join_room(rooms, "carol", room["id"])
        rooms.get_moderation(room["id"]).assign_role("bob", ROLE_MODERATOR, actor_id="host1")
        rooms.get_moderation(room["id"]).mute("carol", actor_id="host1")

        await main_module.broadcast_room_state(room["id"])

        state_events = [e for e in fake_sio.emitted if e[0] == "room:state" and e[2] == f"room:{room['id']}"]
        assert state_events
        players = {p["id"]: p for p in state_events[-1][1]["players"]}
        assert players["host1"]["role"] == "owner"
        assert players["bob"]["role"] == "moderator"
        assert players["carol"]["role"] == "participant"
        assert players["carol"]["muted"] is True
        assert players["bob"]["muted"] is False


class TestMuteHandlers:
    async def test_moderator_can_mute_a_user_and_chat_is_blocked(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "mod1", room["id"])
        await _join_room(rooms, "carol", room["id"])
        rooms.get_moderation(room["id"]).assign_role("mod1", ROLE_MODERATOR, actor_id="host1")

        await main_module.room_moderation_mute("mod1", {"targetId": "carol"})
        assert rooms.get_moderation(room["id"]).is_muted("carol") is True

        await main_module.chat_send("carol", {"text": "hello", "type": "public"})
        chat_events = [e for e in fake_sio.emitted if e[0] == "chat:message"]
        assert not chat_events, "muted user's message must not be broadcast"
        error_events = [e for e in fake_sio.emitted if e[0] == "error"]
        assert error_events

    async def test_participant_cannot_mute(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "bob", room["id"])
        await _join_room(rooms, "carol", room["id"])

        await main_module.room_moderation_mute("bob", {"targetId": "carol"})

        assert rooms.get_moderation(room["id"]).is_muted("carol") is False
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_unmuted_user_can_chat_normally(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "carol", room["id"])

        await main_module.chat_send("carol", {"text": "hello", "type": "public"})
        assert any(e[0] == "chat:message" for e in fake_sio.emitted)


class TestKickAndBanHandlers:
    async def test_moderator_can_kick_a_user_out_of_the_room(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "mod1", room["id"])
        await _join_room(rooms, "carol", room["id"])
        rooms.get_moderation(room["id"]).assign_role("mod1", ROLE_MODERATOR, actor_id="host1")

        await main_module.room_moderation_kick("mod1", {"targetId": "carol"})

        assert rooms.get_player_room_id("carol") != room["id"]

    async def test_kicked_player_receives_updated_room_info_for_lobby(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "mod1", room["id"])
        await _join_room(rooms, "carol", room["id"])
        rooms.get_moderation(room["id"]).assign_role("mod1", ROLE_MODERATOR, actor_id="host1")

        await main_module.room_moderation_kick("mod1", {"targetId": "carol"})

        removed_events = [e for e in fake_sio.emitted if e[0] == "room:moderation:removed" and e[2] == "carol"]
        assert removed_events
        payload = removed_events[-1][1]
        assert payload["reason"] == "kicked"
        assert payload["newRoomId"] == "lobby"
        assert payload["hostId"] == rooms.get_room_host_id("lobby")
        assert payload["myRole"] == "participant"
        assert "tiles" in payload
        assert "currentTile" in payload

        lobby_state_events = [e for e in fake_sio.emitted if e[0] == "room:state" and e[2] == "room:lobby"]
        assert lobby_state_events
        assert any(p["id"] == "carol" for p in lobby_state_events[-1][1]["players"])

        chat_history_events = [e for e in fake_sio.emitted if e[0] == "chat:history" and e[2] == "carol"]
        assert chat_history_events

    async def test_moderator_can_ban_a_user_preventing_rejoin(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "mod1", room["id"])
        await _join_room(rooms, "carol", room["id"])
        rooms.get_moderation(room["id"]).assign_role("mod1", ROLE_MODERATOR, actor_id="host1")

        await main_module.room_moderation_ban("mod1", {"targetId": "carol"})

        assert rooms.get_room_join_error("carol", room["id"]) == "banned"

    async def test_participant_cannot_kick_or_ban(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "bob", room["id"])
        await _join_room(rooms, "carol", room["id"])

        await main_module.room_moderation_kick("bob", {"targetId": "carol"})
        await main_module.room_moderation_ban("bob", {"targetId": "carol"})

        assert rooms.get_player_room_id("carol") == room["id"]
        assert rooms.get_room_join_error("carol", room["id"]) is None

    async def test_banned_player_cannot_rejoin_room_via_room_join_handler(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "mod1", room["id"])
        await _join_room(rooms, "carol", room["id"])
        rooms.get_moderation(room["id"]).assign_role("mod1", ROLE_MODERATOR, actor_id="host1")
        await main_module.room_moderation_ban("mod1", {"targetId": "carol"})

        fake_sio.emitted.clear()
        await main_module.room_join("carol", {"roomId": room["id"]})

        assert rooms.get_player_room_id("carol") != room["id"]
        error_events = [e for e in fake_sio.emitted if e[0] == "error" and e[2] == "carol"]
        assert error_events
        assert "banned" in error_events[-1][1]["message"].lower()


class TestContentReportHandler:
    async def test_any_participant_can_report_content(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "carol", room["id"])

        result = await main_module.room_moderation_report("carol", {
            "targetType": "chat_message", "targetId": "msg-1", "reason": "spam",
        })

        assert result["reporterId"] == "carol"

    async def test_moderator_can_list_reports_but_participant_cannot(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "mod1", room["id"])
        await _join_room(rooms, "carol", room["id"])
        rooms.get_moderation(room["id"]).assign_role("mod1", ROLE_MODERATOR, actor_id="host1")
        await main_module.room_moderation_report("carol", {
            "targetType": "chat_message", "targetId": "msg-1", "reason": "spam",
        })

        reports = await main_module.room_moderation_reports_request("mod1", {})
        assert len(reports) == 1

        fake_sio.emitted.clear()
        forbidden = await main_module.room_moderation_reports_request("carol", {})
        assert forbidden is None
        assert any(e[0] == "error" for e in fake_sio.emitted)


class TestAuditLogHandler:
    async def test_moderator_can_view_audit_log(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "mod1", room["id"])
        rooms.get_moderation(room["id"]).assign_role("mod1", ROLE_MODERATOR, actor_id="host1")

        log = await main_module.room_moderation_audit_log_request("mod1", {})
        assert any(entry["action"] == "assign_role" for entry in log)

    async def test_participant_cannot_view_audit_log(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "bob", room["id"])

        result = await main_module.room_moderation_audit_log_request("bob", {})
        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)


class TestExternalLinksPolicyHandler:
    async def test_owner_can_disable_external_links(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)

        result = await main_module.room_moderation_external_links_set("host1", {"allowed": False})

        assert result["allowed"] is False
        assert rooms.get_moderation(room["id"]).are_external_links_allowed() is False

    async def test_non_owner_cannot_change_external_links_policy(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "bob", room["id"])

        await main_module.room_moderation_external_links_set("bob", {"allowed": False})

        assert rooms.get_moderation(room["id"]).are_external_links_allowed() is True
        assert any(e[0] == "error" for e in fake_sio.emitted)


class TestExternalLinksChatEnforcement:
    async def test_chat_with_url_is_blocked_when_links_disallowed(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "carol", room["id"])
        rooms.get_moderation(room["id"]).set_external_links_allowed(False, actor_id="host1")

        await main_module.chat_send("carol", {"text": "check http://example.com", "type": "public"})

        assert not [e for e in fake_sio.emitted if e[0] == "chat:message"]
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_chat_with_url_allowed_by_default(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "carol", room["id"])

        await main_module.chat_send("carol", {"text": "check http://example.com", "type": "public"})

        assert any(e[0] == "chat:message" for e in fake_sio.emitted)

    async def test_chat_without_url_allowed_when_links_disallowed(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        await _join_room(rooms, "carol", room["id"])
        rooms.get_moderation(room["id"]).set_external_links_allowed(False, actor_id="host1")

        await main_module.chat_send("carol", {"text": "hello everyone", "type": "public"})

        assert any(e[0] == "chat:message" for e in fake_sio.emitted)


class TestRoomJoinedPayloadIncludesRoleInfo:
    async def test_room_joined_includes_host_id_and_my_role_for_owner(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("host1", avatar, "lobby")
        room = rooms.create_room(host_id="host1", name="Edu Room")

        await main_module.room_join("host1", {"roomId": room["id"]})

        joined_events = [e for e in fake_sio.emitted if e[0] == "room:joined" and e[2] == "host1"]
        assert joined_events
        payload = joined_events[-1][1]
        assert payload["hostId"] == "host1"
        assert payload["myRole"] == "owner"

    async def test_room_joined_includes_participant_role_for_regular_player(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room = await _make_room_with_host(rooms)
        avatar = create_default_avatar("Bob")
        rooms.join_room("bob", avatar, "lobby")

        await main_module.room_join("bob", {"roomId": room["id"]})

        joined_events = [e for e in fake_sio.emitted if e[0] == "room:joined" and e[2] == "bob"]
        assert joined_events
        payload = joined_events[-1][1]
        assert payload["hostId"] == "host1"
        assert payload["myRole"] == "participant"
