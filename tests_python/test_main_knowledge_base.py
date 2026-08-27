"""TDD tests for the character knowledge-store socket handlers in
server/main.py: `room:character:knowledge_base:title:set`,
`room:character:knowledge_base:document:add`, and
`room:character:knowledge_base:document:remove`.

These handlers replaced the earlier single free-text `knowledge_base:set`
event (section 22.3 of the feature design calls for a multi-document
knowledge store per character, not one blob of text), and this file
exercises the full journey through the socket-handler layer: create an
ai_character object, configure it, manage its knowledge documents, and
confirm permission/validation errors are surfaced to the client via the
generic `error` emit -- the same contract every other builder handler in
this file follows.
"""
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
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)

    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    return fresh_rooms, fake_sio


async def _make_character(rooms, host_id="p1"):
    rooms.join_room(host_id, create_default_avatar("Alice"), "lobby")
    npc = await main_module.room_object_create(host_id, {
        "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
    })
    await main_module.room_character_configure(host_id, {
        "objectId": npc["objectId"], "name": "Owl", "role": "guide", "startNodeId": "node-1",
    })
    return npc["objectId"]


class TestKnowledgeBaseTitleSet:
    async def test_sets_title(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)

        character = await main_module.room_character_knowledge_base_title_set("p1", {
            "objectId": object_id, "title": "Owl Facts",
        })

        assert character["knowledgeBase"]["title"] == "Owl Facts"

    async def test_denied_for_non_owner_non_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        rooms.join_room("p2", create_default_avatar("Bob"), "lobby")

        result = await main_module.room_character_knowledge_base_title_set("p2", {
            "objectId": object_id, "title": "Hijacked",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_requires_joined_room(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        result = await main_module.room_character_knowledge_base_title_set("stranger", {
            "objectId": "anything", "title": "x",
        })
        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)


class TestKnowledgeBaseDocumentAdd:
    async def test_adds_text_document(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)

        character = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })

        assert character["knowledgeBase"]["documents"][0]["title"] == "Habitat"
        assert character["knowledgeBase"]["documents"][0]["content"] == "Owls live in forests."

    async def test_adds_link_document(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)

        character = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "More info", "docType": "link", "url": "https://example.com/owls",
        })

        assert character["knowledgeBase"]["documents"][0]["url"] == "https://example.com/owls"

    async def test_rejects_link_with_unsafe_url(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)

        result = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Internal", "docType": "link", "url": "http://127.0.0.1/secret",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_rejects_invalid_doc_type(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)

        result = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Bad", "docType": "video", "content": "x",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_denied_for_non_owner_non_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        rooms.join_room("p2", create_default_avatar("Bob"), "lobby")

        result = await main_module.room_character_knowledge_base_document_add("p2", {
            "objectId": object_id, "title": "Hijacked", "docType": "text", "content": "x",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_generates_doc_id_when_omitted(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)

        character = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })

        assert character["knowledgeBase"]["documents"][0]["docId"]


class TestKnowledgeBaseDocumentRemove:
    async def test_removes_document(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        added = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })
        doc_id = added["knowledgeBase"]["documents"][0]["docId"]

        character = await main_module.room_character_knowledge_base_document_remove("p1", {
            "objectId": object_id, "docId": doc_id,
        })

        assert character["knowledgeBase"]["documents"] == []

    async def test_unknown_doc_id_surfaces_error(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)

        result = await main_module.room_character_knowledge_base_document_remove("p1", {
            "objectId": object_id, "docId": "unknown-doc",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_denied_for_non_owner_non_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        added = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })
        doc_id = added["knowledgeBase"]["documents"][0]["docId"]
        rooms.join_room("p2", create_default_avatar("Bob"), "lobby")

        result = await main_module.room_character_knowledge_base_document_remove("p2", {
            "objectId": object_id, "docId": doc_id,
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)


class TestKnowledgeBaseDocumentUpdate:
    async def test_updates_document_fields(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        added = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })
        doc_id = added["knowledgeBase"]["documents"][0]["docId"]

        character = await main_module.room_character_knowledge_base_document_update("p1", {
            "objectId": object_id, "docId": doc_id, "title": "Habitat (updated)",
            "docType": "text", "content": "Owls live in forests and deserts.",
        })

        doc = character["knowledgeBase"]["documents"][0]
        assert doc["title"] == "Habitat (updated)"
        assert doc["content"] == "Owls live in forests and deserts."

    async def test_can_change_doc_type_to_link(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        added = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })
        doc_id = added["knowledgeBase"]["documents"][0]["docId"]

        character = await main_module.room_character_knowledge_base_document_update("p1", {
            "objectId": object_id, "docId": doc_id, "title": "Habitat",
            "docType": "link", "url": "https://example.com/habitat",
        })

        doc = character["knowledgeBase"]["documents"][0]
        assert doc["docType"] == "link"
        assert doc["url"] == "https://example.com/habitat"

    async def test_rejects_unsafe_link_url(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        added = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })
        doc_id = added["knowledgeBase"]["documents"][0]["docId"]

        result = await main_module.room_character_knowledge_base_document_update("p1", {
            "objectId": object_id, "docId": doc_id, "title": "Habitat",
            "docType": "link", "url": "http://127.0.0.1/secret",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_unknown_doc_id_surfaces_error(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)

        result = await main_module.room_character_knowledge_base_document_update("p1", {
            "objectId": object_id, "docId": "unknown-doc", "title": "x", "docType": "text", "content": "x",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_denied_for_non_owner_non_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        added = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })
        doc_id = added["knowledgeBase"]["documents"][0]["docId"]
        rooms.join_room("p2", create_default_avatar("Bob"), "lobby")

        result = await main_module.room_character_knowledge_base_document_update("p2", {
            "objectId": object_id, "docId": doc_id, "title": "Hijacked", "docType": "text", "content": "x",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)


class TestKnowledgeBaseDocumentReorder:
    async def test_moves_document_up(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "A", "docType": "text", "content": "a",
        })
        added_b = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "B", "docType": "text", "content": "b",
        })
        doc_b_id = added_b["knowledgeBase"]["documents"][1]["docId"]

        character = await main_module.room_character_knowledge_base_document_reorder("p1", {
            "objectId": object_id, "docId": doc_b_id, "direction": "up",
        })

        assert [d["title"] for d in character["knowledgeBase"]["documents"]] == ["B", "A"]

    async def test_rejects_invalid_direction(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        added = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "A", "docType": "text", "content": "a",
        })
        doc_id = added["knowledgeBase"]["documents"][0]["docId"]

        result = await main_module.room_character_knowledge_base_document_reorder("p1", {
            "objectId": object_id, "docId": doc_id, "direction": "sideways",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)

    async def test_denied_for_non_owner_non_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "A", "docType": "text", "content": "a",
        })
        added_b = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "B", "docType": "text", "content": "b",
        })
        doc_b_id = added_b["knowledgeBase"]["documents"][1]["docId"]
        rooms.join_room("p2", create_default_avatar("Bob"), "lobby")

        result = await main_module.room_character_knowledge_base_document_reorder("p2", {
            "objectId": object_id, "docId": doc_b_id, "direction": "up",
        })

        assert result is None
        assert any(e[0] == "error" for e in fake_sio.emitted)


class TestGenerativeAskUsesKnowledgeDocuments:
    async def test_ask_generative_forwards_combined_knowledge_context(self, isolate_registry, monkeypatch):
        rooms, fake_sio = isolate_registry
        # Generative AI settings are restricted to the room admin (Phase I),
        # so this must be a real room where p1 is the host, not just a
        # lobby member.
        room = rooms.create_room(host_id="p1", name="Owl's Room")
        rooms.join_room("p1", create_default_avatar("Alice"), room["id"])
        npc = await main_module.room_object_create("p1", {
            "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        object_id = npc["objectId"]
        await main_module.room_character_configure("p1", {
            "objectId": object_id, "name": "Owl", "role": "guide", "startNodeId": "node-1",
        })
        await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })
        generative_config = await main_module.room_character_generative_configure("p1", {
            "objectId": object_id, "apiBaseUrl": "https://api.example.com", "apiKey": "secret",
        })
        assert generative_config["generativeEnabled"] is True

        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None, follow_redirects=None):
            captured["messages"] = json["messages"]

            class FakeResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"choices": [{"message": {"content": "A generated answer."}}]}

            return FakeResponse()

        monkeypatch.setattr(main_module.httpx, "post", fake_post)

        result = await main_module.room_character_ask("p1", {
            "objectId": object_id, "userMessage": "Tell me about owls",
        })

        assert result["answer"] == "A generated answer."
        system_messages = [m["content"] for m in captured["messages"] if m["role"] == "system"]
        assert any("Owls live in forests." in m for m in system_messages)


class TestKnowledgeStoreEndToEndJourney:
    """Exercises the full knowledge-store vertical slice through the same
    socket-handler layer the client talks to: configure a character, set a
    knowledge-base title, add a text and a link document, ask a question in
    generative mode (verifying the combined context reaches the model
    caller), remove a document, and confirm the final persisted state.
    """

    async def test_full_knowledge_store_journey(self, isolate_registry, monkeypatch):
        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="p1", name="Owl's Room")
        rooms.join_room("p1", create_default_avatar("Alice"), room["id"])

        npc = await main_module.room_object_create("p1", {
            "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        object_id = npc["objectId"]
        await main_module.room_character_configure("p1", {
            "objectId": object_id, "name": "Owl", "role": "guide", "startNodeId": "node-1",
        })

        # 1. Set the knowledge-base title.
        character = await main_module.room_character_knowledge_base_title_set("p1", {
            "objectId": object_id, "title": "Owl Facts",
        })
        assert character["knowledgeBase"]["title"] == "Owl Facts"

        # 2. Add a text document and a link document.
        character = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "Habitat", "docType": "text", "content": "Owls live in forests.",
        })
        character = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": object_id, "title": "More info", "docType": "link", "url": "https://example.com/owls",
        })
        assert len(character["knowledgeBase"]["documents"]) == 2
        text_doc_id = character["knowledgeBase"]["documents"][0]["docId"]
        link_doc_id = character["knowledgeBase"]["documents"][1]["docId"]

        # 2b. Reorder: move the link doc up, then back down -- confirm the
        # reorder handler works and restores the original order used below.
        character = await main_module.room_character_knowledge_base_document_reorder("p1", {
            "objectId": object_id, "docId": link_doc_id, "direction": "up",
        })
        assert [d["docId"] for d in character["knowledgeBase"]["documents"]] == [link_doc_id, text_doc_id]
        character = await main_module.room_character_knowledge_base_document_reorder("p1", {
            "objectId": object_id, "docId": link_doc_id, "direction": "down",
        })
        assert [d["docId"] for d in character["knowledgeBase"]["documents"]] == [text_doc_id, link_doc_id]

        # 3. Enable generative mode and ask a question -- confirm the
        # combined knowledge context (title + text doc + link) reaches the
        # model caller.
        generative_config = await main_module.room_character_generative_configure("p1", {
            "objectId": object_id, "apiBaseUrl": "https://api.example.com", "apiKey": "secret",
        })
        assert generative_config["generativeEnabled"] is True

        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None, follow_redirects=None):
            captured["messages"] = json["messages"]

            class FakeResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"choices": [{"message": {"content": "Owls are birds of prey."}}]}

            return FakeResponse()

        monkeypatch.setattr(main_module.httpx, "post", fake_post)

        ask_result = await main_module.room_character_ask("p1", {
            "objectId": object_id, "userMessage": "Tell me about owls",
        })
        assert ask_result["answer"] == "Owls are birds of prey."
        system_context = next(m["content"] for m in captured["messages"] if m["role"] == "system")
        assert "Owl Facts" in system_context
        assert "Owls live in forests." in system_context
        assert "https://example.com/owls" in system_context

        # 4. Update the text document's content in place -- confirm the
        # docId and list position are preserved (unlike remove + re-add).
        character = await main_module.room_character_knowledge_base_document_update("p1", {
            "objectId": object_id, "docId": text_doc_id, "title": "Habitat",
            "docType": "text", "content": "Owls live in forests and deserts.",
        })
        assert [d["docId"] for d in character["knowledgeBase"]["documents"]] == [text_doc_id, link_doc_id]
        assert character["knowledgeBase"]["documents"][0]["content"] == "Owls live in forests and deserts."

        # 5. Remove the link document and confirm only the text document remains.
        character = await main_module.room_character_knowledge_base_document_remove("p1", {
            "objectId": object_id, "docId": link_doc_id,
        })
        assert [d["docId"] for d in character["knowledgeBase"]["documents"]] == [text_doc_id]

        # 6. Final state sanity check via listing on the story engine directly
        # is implicitly covered by the returned character payload above.
        assert character["knowledgeBase"]["title"] == "Owl Facts"
        assert character["knowledgeBase"]["documents"][0]["content"] == "Owls live in forests and deserts."

