"""Security regression tests for the room authoring authorization model.

Background: this app has no authentication -- a player's identity IS their
Socket.IO session id, and anyone can join any public room. Authorization is
therefore entirely server-side, and several authoring handlers used to run
with no privilege check at all, so any visitor could restructure, re-author
or vandalise a room they merely walked into.

These tests pin the fixed behaviour so the gates cannot silently regress.
"""
import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar
from server.game.moderation import ModerationState
from server.game.room_builder import RoomBuilderState


class FakeSio:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data=None, room=None, skip_sid=None):
        self.emitted.append((event, data, room))


@pytest.fixture(autouse=True)
def isolate_registry(monkeypatch):
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)
    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    async def fake_save_message(message, room_id="lobby"):
        return None

    monkeypatch.setattr(main_module.db, "save_message", fake_save_message)
    return fresh_rooms, fake_sio


def _trigger_ids(builder):
    return {t["triggerId"] for t in builder.list_triggers()}


def _host_room_with_visitor(rooms):
    """A room owned by "host" that an unrelated "visitor" has joined."""
    room_id = rooms.create_room(host_id="host", name="Host Room")["id"]
    rooms.join_room("host", create_default_avatar("Host"), room_id)
    rooms.join_room("visitor", create_default_avatar("Mallory"), room_id)
    return room_id


def _errors(fake_sio):
    return [e for e in fake_sio.emitted if e[0] == "error"]


class TestTileManagementIsHostOnly:
    """A visitor could previously add, clone, relabel and -- most damaging --
    DELETE tiles in someone else's room."""

    async def test_visitor_cannot_add_tile(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)

        await main_module.room_tile_add("visitor", {"direction": "right"})

        assert rooms.get_builder(room_id).get_tile((1, 0)) is None
        assert _errors(fake_sio)

    async def test_visitor_cannot_clone_tile(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)

        await main_module.room_tile_clone("visitor", {"direction": "right"})

        assert rooms.get_builder(room_id).get_tile((1, 0)) is None
        assert _errors(fake_sio)

    async def test_visitor_cannot_delete_tile(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)
        rooms.add_neighbor_tile(room_id, (0, 0), "right")

        await main_module.room_tile_delete("visitor", {"x": 1, "y": 0})

        assert rooms.get_builder(room_id).get_tile((1, 0)) is not None
        assert _errors(fake_sio)

    async def test_visitor_cannot_configure_tile(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)

        await main_module.room_tile_configure(
            "visitor", {"x": 0, "y": 0, "label": "Pwned"}
        )

        assert rooms.get_builder(room_id).get_tile((0, 0))["label"] != "Pwned"
        assert _errors(fake_sio)

    async def test_host_can_still_manage_tiles(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)

        await main_module.room_tile_configure("host", {"x": 0, "y": 0, "label": "Foyer"})
        await main_module.room_tile_add("host", {"direction": "right"})

        builder = rooms.get_builder(room_id)
        assert builder.get_tile((0, 0))["label"] == "Foyer"
        assert builder.get_tile((1, 0)) is not None


class TestZoneAndTriggerAuthoringIsHostOnly:
    """The real damage here was an escape-room bypass: a visitor could create
    a zone covering the tile plus a `reveal_object` trigger, walk into it,
    and have the server reveal a hidden item they never solved for -- which
    then satisfies the `requiredItemId` check on a locked escape door."""

    async def test_visitor_cannot_create_zone(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)

        await main_module.room_zone_create("visitor", {
            "zoneId": "z1", "zoneType": "interaction",
            "minX": 0, "minY": 0, "maxX": 800, "maxY": 600,
        })

        assert rooms.get_builder(room_id).get_zone("z1") is None
        assert _errors(fake_sio)

    async def test_visitor_cannot_create_reveal_trigger(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)
        await main_module.room_zone_create("host", {
            "zoneId": "z1", "zoneType": "interaction",
            "minX": 0, "minY": 0, "maxX": 800, "maxY": 600,
        })

        await main_module.room_trigger_create("visitor", {
            "triggerId": "t1", "zoneId": "z1",
            "eventType": "reveal_object", "payload": {"objectId": "secret"},
        })

        assert "t1" not in _trigger_ids(rooms.get_builder(room_id))
        assert _errors(fake_sio)

    async def test_visitor_cannot_delete_host_zone_or_trigger(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)
        await main_module.room_zone_create("host", {
            "zoneId": "z1", "zoneType": "interaction",
            "minX": 0, "minY": 0, "maxX": 50, "maxY": 50,
        })
        await main_module.room_trigger_create("host", {
            "triggerId": "t1", "zoneId": "z1",
            "eventType": "dialogue", "payload": {"nodeId": "n1"},
        })

        await main_module.room_trigger_delete("visitor", {"triggerId": "t1"})
        await main_module.room_zone_delete("visitor", {"zoneId": "z1"})

        builder = rooms.get_builder(room_id)
        assert "t1" in _trigger_ids(builder)
        assert builder.get_zone("z1") is not None


class TestVersionHistoryIsHostOnly:
    async def test_visitor_cannot_save_draft(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)

        await main_module.room_version_save("visitor", {"snapshot": {"tiles": []}})

        assert rooms.get_builder(room_id).list_versions() == []
        assert _errors(fake_sio)

    async def test_visitor_cannot_publish_or_rollback(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)
        await main_module.room_version_save("host", {"snapshot": {"tiles": []}})

        await main_module.room_version_publish("visitor", {"versionNumber": 1})
        assert rooms.get_builder(room_id).list_versions()[0]["isActive"] is False

        before = len(fake_sio.emitted)
        result = await main_module.room_version_rollback("visitor", {"versionNumber": 1})
        assert result is None
        rollbacks = [
            e for e in fake_sio.emitted[before:] if e[0] == "room:builder:rollback"
        ]
        assert not rollbacks, "rollback leaked a snapshot to a non-host"


class TestHiddenItemsAreNotDisclosedOnJoin:
    """`room:join` built its `room:builder:state` payload with the default
    `requester_id=None`, which `_is_visible_to` treats as a trusted internal
    caller -- so the join response shipped every unrevealed hidden item's id
    and exact coordinates straight to the joining visitor. `RoomBuilderState`
    itself was always correct; the bug was the handler not passing identity
    through, so this asserts on the payload builder the handler calls."""

    def _payload_object_ids(self, payload):
        return {o["objectId"] for o in payload["objects"]}

    async def test_join_payload_omits_unrevealed_hidden_items(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)
        rooms.get_builder(room_id).create_object(
            "secret", "hidden_item", (0, 0), x=100, y=100, width=10, height=10
        )

        payload = main_module.builder_state_payload(
            room_id, requester_id="visitor", is_room_host=False
        )

        assert "secret" not in self._payload_object_ids(payload), (
            "an unrevealed hidden_item must not reach a plain visitor"
        )

    async def test_join_payload_still_shows_hidden_items_to_the_host(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)
        rooms.get_builder(room_id).create_object(
            "secret", "hidden_item", (0, 0), x=100, y=100, width=10, height=10
        )

        payload = main_module.builder_state_payload(
            room_id, requester_id="host", is_room_host=True
        )

        assert "secret" in self._payload_object_ids(payload), (
            "the host must still see hidden items in build mode"
        )

    async def test_default_payload_is_the_unsafe_trusted_view(self, isolate_registry):
        # Pins WHY every visitor-facing call site must pass identity: with
        # the defaults the payload is the full internal view. If this ever
        # starts failing, the default became safe and the comments at the
        # call sites should be revisited.
        rooms, _fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)
        rooms.get_builder(room_id).create_object(
            "secret", "hidden_item", (0, 0), x=100, y=100, width=10, height=10
        )

        payload = main_module.builder_state_payload(room_id)

        assert "secret" in self._payload_object_ids(payload)


class TestDuplicateObjectRespectsEditPermission:
    """Duplication skipped the edit-permission gate every other mutation
    honoured. Because the clone is stored with `createdBy = requester` and
    `isLocked = False`, a visitor could launder an `owner_only` object into
    a copy they fully control."""

    def test_visitor_cannot_duplicate_owner_only_object(self):
        builder = RoomBuilderState()
        builder.create_object(
            "o1", "table", (0, 0), x=10, y=10, width=20, height=20, created_by="host"
        )

        with pytest.raises(PermissionError):
            builder.duplicate_object("o1", "o1-copy", requester_id="visitor")

        assert builder.get_object("o1-copy") is None

    def test_room_host_can_duplicate_others_objects(self):
        builder = RoomBuilderState()
        builder.create_object(
            "o1", "table", (0, 0), x=10, y=10, width=20, height=20, created_by="someone"
        )

        clone = builder.duplicate_object(
            "o1", "o1-copy", requester_id="host", is_room_host=True
        )

        assert clone["objectId"] == "o1-copy"

    def test_owner_can_duplicate_their_own_object(self):
        builder = RoomBuilderState()
        builder.create_object(
            "o1", "table", (0, 0), x=10, y=10, width=20, height=20, created_by="owner"
        )

        clone = builder.duplicate_object("o1", "o1-copy", requester_id="owner")

        assert clone["objectId"] == "o1-copy"


class TestModeratorCannotSilenceTheOwner:
    """`kick` and `ban` both refused to target the owner; `mute` did not, so
    an appointed moderator could silence the room owner in their own room."""

    def test_moderator_cannot_mute_owner(self):
        moderation = ModerationState(owner_id="owner")
        moderation.assign_role("mod", "moderator", actor_id="owner")

        with pytest.raises(PermissionError):
            moderation.mute("owner", actor_id="mod")

        assert moderation.is_muted("owner") is False

    def test_moderator_can_still_mute_a_participant(self):
        moderation = ModerationState(owner_id="owner")
        moderation.assign_role("mod", "moderator", actor_id="owner")

        moderation.mute("noisy", actor_id="mod")

        assert moderation.is_muted("noisy") is True


class TestInviteCodeEnforcement:
    def test_wrong_invite_code_is_rejected(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        room = rooms.create_room(
            host_id="host", name="Private", access="invite", invite_code="s3cret"
        )

        assert rooms.get_room_join_error("mallory", room["id"], "wrong") == "forbidden"
        assert rooms.get_room_join_error("mallory", room["id"], None) == "forbidden"
        assert rooms.get_room_join_error("mallory", room["id"], "s3cret") is None

    def test_non_string_invite_code_is_rejected_not_crashed(self, isolate_registry):
        # compare_digest raises TypeError on non-str input, so a malicious
        # client sending a list/dict must be normalised, not crash the join.
        rooms, _fake_sio = isolate_registry
        room = rooms.create_room(
            host_id="host", name="Private", access="invite", invite_code="s3cret"
        )

        assert rooms.get_room_join_error("mallory", room["id"], ["s3cret"]) == "forbidden"
        assert rooms.get_room_join_error("mallory", room["id"], 12345) == "forbidden"


class TestChatMessageTypeIsValidated:
    async def test_unknown_message_type_falls_back_to_public(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = _host_room_with_visitor(rooms)

        await main_module.chat_send("visitor", {"text": "hi", "type": "system"})

        messages = [e for e in fake_sio.emitted if e[0] == "chat:message"]
        assert messages, "message was not delivered"
        assert messages[-1][1]["type"] == "public"

    async def test_chat_send_tolerates_missing_payload(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        _host_room_with_visitor(rooms)

        await main_module.chat_send("visitor", None)
