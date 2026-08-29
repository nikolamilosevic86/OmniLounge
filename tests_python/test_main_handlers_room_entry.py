import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar


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
    """Give each test a clean rooms registry, a fake sio, and stubbed db
    calls so no real network/db access happens during player_join/room_join."""
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)

    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    async def fake_save_avatar(avatar):
        return None

    monkeypatch.setattr(main_module.db, "save_avatar", fake_save_avatar)

    async def fake_save_message(message, room_id="lobby"):
        return None

    monkeypatch.setattr(main_module.db, "save_message", fake_save_message)

    async def fake_get_recent_messages(room_id="lobby", limit=50):
        return []

    monkeypatch.setattr(main_module.db, "get_recent_messages", fake_get_recent_messages)
    return fresh_rooms, fake_sio


def _builder_state_events_to(fake_sio, sid):
    return [e for e in fake_sio.emitted if e[0] == "room:builder:state" and e[2] == sid]


class TestPlayerJoinSendsExistingBuilderState:
    async def test_player_join_sends_builder_state_snapshot_with_existing_lobby_objects(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        lobby_builder = rooms.get_builder("lobby")
        lobby_builder.create_object("bookshelf-1", "bookshelf", (0, 0), x=10, y=10, width=20, height=20)

        avatar = create_default_avatar("Alice")
        await main_module.player_join("alice", {"avatar": avatar})

        events = _builder_state_events_to(fake_sio, "alice")
        assert events, "expected room:builder:state to be sent to the newly joined player"
        object_ids = {o["objectId"] for o in events[-1][1]["objects"]}
        assert "bookshelf-1" in object_ids

    async def test_player_join_still_emits_player_joined_when_no_objects_exist(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Bob")
        await main_module.player_join("bob", {"avatar": avatar})
        joined_events = [e for e in fake_sio.emitted if e[0] == "player:joined" and e[2] == "bob"]
        assert joined_events


class TestPlayerJoinDoesNotDuplicateChatHistory:
    async def test_repeated_joins_do_not_pollute_lobby_messages_or_duplicate_history(self, isolate_registry, monkeypatch):
        """Regression test: player_join used to re-append every persisted
        message into the live in-memory Room on each join, so the Nth player
        to connect saw the same history duplicated N times. It should just
        forward the persisted, filtered history without mutating the room."""
        rooms, fake_sio = isolate_registry

        db_messages = [{
            "id": "msg_1",
            "senderId": "carol",
            "senderName": "Carol",
            "text": "hello",
            "type": "public",
            "recipientId": None,
            "timestamp": 1000,
        }]

        async def fake_get_recent_messages(room_id="lobby", limit=50):
            return list(db_messages)

        monkeypatch.setattr(main_module.db, "get_recent_messages", fake_get_recent_messages)

        await main_module.player_join("alice", {"avatar": create_default_avatar("Alice")})
        fake_sio.emitted.clear()
        await main_module.player_join("bob", {"avatar": create_default_avatar("Bob")})

        lobby = rooms.get_room("lobby")
        assert lobby.get_messages() == []

        history_events = [e for e in fake_sio.emitted if e[0] == "chat:history" and e[2] == "bob"]
        assert history_events
        assert history_events[-1][1] == db_messages


class TestRoomJoinSendsExistingBuilderState:
    async def test_room_join_sends_builder_state_snapshot_with_existing_objects(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("alice", avatar, "lobby")
        room = rooms.create_room(host_id="alice", name="Study Hall")

        builder = rooms.get_builder(room["id"])
        builder.create_object("tv-1", "tv", (0, 0), x=15, y=15, width=30, height=30)

        fake_sio.emitted.clear()
        avatar_bob = create_default_avatar("Bob")
        rooms.join_room("bob", avatar_bob, "lobby")
        await main_module.room_join("bob", {"roomId": room["id"]})

        events = _builder_state_events_to(fake_sio, "bob")
        assert events, "expected room:builder:state to be sent to the joining player"
        object_ids = {o["objectId"] for o in events[-1][1]["objects"]}
        assert "tv-1" in object_ids

    async def test_room_join_builder_state_snapshot_is_scoped_to_the_joined_room(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar_bob = create_default_avatar("Bob")
        rooms.join_room("bob", avatar_bob, "lobby")
        room = rooms.create_room(host_id="bob", name="Study Hall")

        fake_sio.emitted.clear()
        await main_module.room_join("bob", {"roomId": room["id"]})

        events = _builder_state_events_to(fake_sio, "bob")
        assert events
        assert events[-1][1]["roomId"] == room["id"]
