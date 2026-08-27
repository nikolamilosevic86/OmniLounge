"""Phase K: end-to-end integration scenario for a *learner* journey through
the socket-handler layer, complementing the creator-focused
`TestKnowledgeStoreEndToEndJourney` in test_main_knowledge_base.py.

A room host/creator builds out a room (bookshelf with a book, AI story
character with a node) and a separate learner joins that room, moves
around, talks to the character, reads and saves progress on the book, and
sends a chat message that's broadcast to the room -- exercising
room_builder.py, bookshelf.py, story.py, rooms_registry.py, and the chat
path together through server/main.py's public handler functions, the same
way a real client would drive them one event at a time.
"""
import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar
from server.game.rooms_registry import RoomsRegistry


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
    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)

    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    saved_messages = []

    async def fake_save_message(message, room_id="lobby"):
        saved_messages.append((room_id, message))

    async def fake_get_recent_messages(room_id="lobby", limit=50):
        return []

    async def fake_save_avatar(avatar):
        return None

    monkeypatch.setattr(main_module.db, "save_message", fake_save_message)
    monkeypatch.setattr(main_module.db, "get_recent_messages", fake_get_recent_messages)
    monkeypatch.setattr(main_module.db, "save_avatar", fake_save_avatar)

    return fresh_rooms, fake_sio, saved_messages


class TestLearnerJourneyEndToEnd:
    async def test_learner_joins_room_reads_book_talks_to_character_and_chats(self, isolate_registry):
        rooms, fake_sio, saved_messages = isolate_registry

        # 1. The creator/host sets up a study room with a bookshelf book
        # and a guide character with one predefined story node.
        host_avatar = create_default_avatar("Hosty")
        rooms.join_room("host", host_avatar, "lobby")
        room = rooms.create_room(host_id="host", name="Owl Study Room")
        room_id = room["id"]
        builder = rooms.get_builder(room_id)

        # room_object_create/room_book_add/etc. read the caller's *current*
        # room+tile from the registry, so the host must actually be joined
        # to the new room (not just its creator) before authoring objects.
        rooms.join_room("host", host_avatar, room_id)

        shelf = await main_module.room_object_create("host", {
            "objectType": "bookshelf", "x": 5, "y": 5, "width": 20, "height": 20,
        })
        book = await main_module.room_book_add("host", {
            "objectId": shelf["objectId"], "bookId": "book-1", "title": "Owls of the World",
            "contentBody": "Owls are nocturnal birds of prey.",
        })
        assert book["title"] == "Owls of the World"

        npc = await main_module.room_object_create("host", {
            "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_character_configure("host", {
            "objectId": npc["objectId"], "name": "Owl", "role": "guide", "startNodeId": "node-1",
        })
        await main_module.room_character_node_add("host", {
            "objectId": npc["objectId"], "nodeId": "node-1",
            "characterLine": "Hello, curious learner! Ask me about owls.",
        })

        # 2. A separate learner joins the app (lobby), then joins the room.
        learner_avatar = create_default_avatar("Lea")
        rooms.join_room("learner", learner_avatar, "lobby")
        fake_sio.emitted.clear()
        joined = await main_module.room_join("learner", {"roomId": room_id})
        assert joined is None  # room_join has no return value; success is via emits
        joined_events = [e for e in fake_sio.emitted if e[0] == "room:joined" and e[2] == "learner"]
        assert joined_events and joined_events[-1][1]["roomId"] == room_id

        # 3. The learner walks toward the character.
        moving = await main_module.player_move("learner", {"x": 12, "y": 12})
        assert moving is None
        moving_events = [e for e in fake_sio.emitted if e[0] == "player:moving"]
        assert moving_events and moving_events[-1][1]["id"] == "learner"

        # 4. The learner talks to the guide character and receives the
        # predefined story node (no generative mode configured).
        talk_result = await main_module.room_character_talk("learner", {"objectId": npc["objectId"]})
        assert talk_result["mode"] == "predefined"
        assert talk_result["node"]["characterLine"] == "Hello, curious learner! Ask me about owls."

        # 5. The learner reads the bookshelf book and saves progress.
        progress = await main_module.room_book_progress_save("learner", {
            "objectId": shelf["objectId"], "bookId": "book-1", "progress": 0.5,
        })
        assert progress["progress"] == 0.5

        # 6. The learner sends a room chat message, which is broadcast to
        # the room channel and persisted.
        fake_sio.emitted.clear()
        await main_module.chat_send("learner", {"text": "Owls are so cool!"})
        chat_events = [e for e in fake_sio.emitted if e[0] == "chat:message"]
        assert chat_events, "expected a chat:message broadcast"
        assert chat_events[-1][1]["text"] == "Owls are so cool!"
        assert chat_events[-1][2] == main_module.room_channel(room_id)
        assert saved_messages and saved_messages[-1][0] == room_id

        # 7. Sanity check: the room's builder state (as the client would
        # re-fetch it) still contains both authored objects.
        object_ids = {o["objectId"] for o in builder.list_objects()}
        assert {shelf["objectId"], npc["objectId"]} <= object_ids
