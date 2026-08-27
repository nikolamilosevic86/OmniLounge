import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar


class FakeSio:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data=None, room=None, skip_sid=None):
        self.emitted.append((event, data, room))


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
    return fresh_rooms, fake_sio


class TestChatSendBroadcastsBubbles:
    async def test_chat_send_does_not_raise_and_scopes_bubbles_to_room(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        # Regression test: chat_send previously called broadcast_bubbles()
        # with no room_id argument, which raised TypeError at runtime.
        await main_module.chat_send("p1", {"text": "hello", "type": "public"})

        bubble_events = [e for e in fake_sio.emitted if e[0] == "chat:bubbles"]
        assert bubble_events, "expected chat:bubbles to be emitted after chat:send"

    async def test_chat_send_truncates_text_beyond_max_length_server_side(self, isolate_registry):
        # Security: the client enforces maxlength=200 on the chat input, but a
        # raw/malicious socket client can send arbitrarily long text; the
        # server must not trust client-side-only validation.
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        overlong_text = "a" * 5000
        await main_module.chat_send("p1", {"text": overlong_text, "type": "public"})

        message_events = [e for e in fake_sio.emitted if e[0] == "chat:message"]
        assert message_events, "expected chat:message to be emitted"
        assert len(message_events[-1][1]["text"]) <= 200


class TestApplyPlayerMovement:
    def test_bot_id_player_still_moves_toward_target(self, isolate_registry):
        rooms, _ = isolate_registry
        from server.game.ai_bot import BOT_ID, BOT_AVATAR

        lobby = rooms.get_room("lobby")
        bot = lobby.add_player(BOT_ID, BOT_AVATAR)
        # Use an obstacle-free region (obstacles live around y >= 330).
        bot["position"] = {"x": 100.0, "y": 150.0}
        bot["targetPosition"] = {"x": 200.0, "y": 150.0}

        moved = main_module.apply_player_movement(lobby, "lobby", bot, now_ms=0)

        assert moved is True
        assert bot["position"]["x"] > 100.0

    def test_regular_player_moves_by_direction(self, isolate_registry):
        rooms, _ = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")
        lobby = rooms.get_room("lobby")
        player = lobby.get_player("p1")
        player["position"] = {"x": 400.0, "y": 300.0}
        player["direction"] = {"x": 1, "y": 0}

        moved = main_module.apply_player_movement(lobby, "lobby", player, now_ms=0)

        assert moved is True
        assert player["position"]["x"] > 400.0


class TestRoomBuilderHandlers:
    async def _join(self, rooms, player_id="p1"):
        avatar = create_default_avatar("Alice")
        rooms.join_room(player_id, avatar, "lobby")

    def _builder_state_events(self, fake_sio):
        return [e for e in fake_sio.emitted if e[0] == "room:builder:state"]

    async def test_tile_clone_and_configure_and_delete(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        await main_module.room_tile_configure("p1", {"x": 0, "y": 0, "label": "Entrance"})
        builder = rooms.get_builder("lobby")
        assert builder.get_tile((0, 0))["label"] == "Entrance"

        await main_module.room_tile_clone("p1", {"direction": "right"})
        assert builder.get_tile((1, 0)) is not None
        assert builder.get_tile((1, 0))["label"] == "Entrance"

        await main_module.room_tile_delete("p1", {"x": 1, "y": 0})
        assert builder.get_tile((1, 0)) is None
        assert self._builder_state_events(fake_sio), "expected builder state broadcasts"

    async def test_object_create_move_duplicate_lock_delete(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        created = await main_module.room_object_create("p1", {
            "objectId": "o1", "objectType": "bookshelf",
            "x": 100, "y": 100, "width": 40, "height": 60,
        })
        assert created["objectId"] == "o1"

        await main_module.room_object_move("p1", {"objectId": "o1", "x": 150, "y": 160})
        builder = rooms.get_builder("lobby")
        assert builder.get_object("o1")["x"] == 150

        await main_module.room_object_lock("p1", {"objectId": "o1", "locked": True})
        assert builder.get_object("o1")["isLocked"] is True

        # locked object rejects move, emits error instead of raising
        await main_module.room_object_move("p1", {"objectId": "o1", "x": 999, "y": 999})
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

        dup = await main_module.room_object_duplicate("p1", {"objectId": "o1", "newObjectId": "o1-copy"})
        assert dup["isLocked"] is False

        await main_module.room_object_lock("p1", {"objectId": "o1", "locked": False})
        await main_module.room_object_delete("p1", {"objectId": "o1"})
        assert builder.get_object("o1") is None

    async def test_object_create_uses_catalog_default_size_and_records_creator(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        created = await main_module.room_object_create("p1", {
            "objectType": "chair", "x": 10, "y": 10,
        })
        assert created["createdBy"] == "p1"
        assert created["sizePreset"] == "S"
        assert created["editPermission"] == "owner_only"

    async def test_object_edit_denied_for_other_participant_by_default(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms, "p1")
        await self._join(rooms, "p2")

        created = await main_module.room_object_create("p1", {
            "objectType": "table", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_object_move("p2", {"objectId": created["objectId"], "x": 500, "y": 500})

        builder = rooms.get_builder("lobby")
        assert builder.get_object(created["objectId"])["x"] == 10
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

    async def test_room_host_can_edit_others_objects(self, isolate_registry):
        from server.game.avatar import create_default_avatar

        rooms, fake_sio = isolate_registry
        room = rooms.create_room(host_id="host-1", name="Test Room")
        room_id = room["id"]
        rooms.join_room("host-1", create_default_avatar("Host"), room_id)
        rooms.join_room("p1", create_default_avatar("Alice"), room_id)

        created = await main_module.room_object_create("p1", {
            "objectType": "table", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_object_move("host-1", {"objectId": created["objectId"], "x": 500, "y": 500})

        builder = rooms.get_builder(room_id)
        assert builder.get_object(created["objectId"])["x"] == 500

    async def test_object_style_update(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        created = await main_module.room_object_create("p1", {
            "objectType": "sofa", "x": 10, "y": 10, "width": 40, "height": 40,
        })
        updated = await main_module.room_object_style("p1", {
            "objectId": created["objectId"], "color": "navy", "material": "fabric",
        })
        assert updated["color"] == "navy"
        assert updated["material"] == "fabric"

    async def test_object_permission_update_then_allows_other_participant(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms, "p1")
        await self._join(rooms, "p2")

        created = await main_module.room_object_create("p1", {
            "objectType": "table", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_object_permission("p1", {
            "objectId": created["objectId"], "editPermission": "anyone",
        })
        await main_module.room_object_move("p2", {"objectId": created["objectId"], "x": 300, "y": 300})

        builder = rooms.get_builder("lobby")
        assert builder.get_object(created["objectId"])["x"] == 300

    async def test_object_interact_emits_result_to_caller(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        created = await main_module.room_object_create("p1", {
            "objectType": "chair", "x": 10, "y": 10, "width": 20, "height": 20,
            "config": {"seatColor": "red"},
        })
        result = await main_module.room_object_interact("p1", {
            "objectId": created["objectId"], "interactionType": "sit",
        })
        assert result["interactionType"] == "sit"
        assert result["payload"] == {"seatColor": "red"}
        interacted_events = [e for e in fake_sio.emitted if e[0] == "room:object:interacted"]
        assert interacted_events and interacted_events[-1][2] == "p1"

    async def test_object_interact_rejects_unsupported_interaction(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        created = await main_module.room_object_create("p1", {
            "objectType": "table", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_object_interact("p1", {
            "objectId": created["objectId"], "interactionType": "watch_video",
        })
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

    async def test_book_add_then_browse_books_interaction_returns_it(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        shelf = await main_module.room_object_create("p1", {
            "objectType": "bookshelf", "x": 10, "y": 10, "width": 40, "height": 60,
        })
        book = await main_module.room_book_add("p1", {
            "objectId": shelf["objectId"], "bookId": "book-1", "title": "Intro",
            "contentBody": "Once upon a time...",
        })
        assert book["bookId"] == "book-1"

        result = await main_module.room_object_interact("p1", {
            "objectId": shelf["objectId"], "interactionType": "browse_books",
        })
        assert [b["bookId"] for b in result["payload"]["books"]] == ["book-1"]

    async def test_book_add_denied_for_non_owner_non_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms, "p1")
        await self._join(rooms, "p2")

        shelf = await main_module.room_object_create("p1", {
            "objectType": "bookshelf", "x": 10, "y": 10, "width": 40, "height": 60,
        })
        await main_module.room_book_add("p2", {
            "objectId": shelf["objectId"], "bookId": "book-1", "title": "Intro",
            "contentBody": "body",
        })
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

    async def test_book_remove(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        shelf = await main_module.room_object_create("p1", {
            "objectType": "bookshelf", "x": 10, "y": 10, "width": 40, "height": 60,
        })
        await main_module.room_book_add("p1", {
            "objectId": shelf["objectId"], "bookId": "book-1", "title": "Intro",
            "contentBody": "body",
        })
        removed = await main_module.room_book_remove("p1", {
            "objectId": shelf["objectId"], "bookId": "book-1",
        })
        assert removed is True

    async def test_book_progress_save_and_resume_reading_interaction(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        shelf = await main_module.room_object_create("p1", {
            "objectType": "bookshelf", "x": 10, "y": 10, "width": 40, "height": 60,
        })
        await main_module.room_book_add("p1", {
            "objectId": shelf["objectId"], "bookId": "book-1", "title": "Intro",
            "contentBody": "body",
        })
        await main_module.room_book_progress_save("p1", {
            "objectId": shelf["objectId"], "bookId": "book-1", "progress": 0.5,
        })

        result = await main_module.room_object_interact("p1", {
            "objectId": shelf["objectId"], "interactionType": "resume_reading",
        })
        assert result["payload"]["book"]["bookId"] == "book-1"
        assert result["payload"]["progress"] == 0.5

    async def test_video_add_then_open_playlist_interaction_returns_it(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        tv = await main_module.room_object_create("p1", {
            "objectType": "tv", "x": 10, "y": 10, "width": 40, "height": 30,
        })
        video = await main_module.room_media_video_add("p1", {
            "objectId": tv["objectId"], "videoId": "video-1", "title": "Lesson",
            "youtubeVideoId": "dQw4w9WgXcQ",
        })
        assert video["videoId"] == "video-1"

        result = await main_module.room_object_interact("p1", {
            "objectId": tv["objectId"], "interactionType": "open_playlist",
        })
        assert [v["videoId"] for v in result["payload"]["videos"]] == ["video-1"]

    async def test_video_add_denied_for_non_owner_non_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms, "p1")
        await self._join(rooms, "p2")

        tv = await main_module.room_object_create("p1", {
            "objectType": "tv", "x": 10, "y": 10, "width": 40, "height": 30,
        })
        await main_module.room_media_video_add("p2", {
            "objectId": tv["objectId"], "videoId": "video-1", "title": "Lesson",
            "youtubeVideoId": "dQw4w9WgXcQ",
        })
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

    async def test_video_remove(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        tv = await main_module.room_object_create("p1", {
            "objectType": "tv", "x": 10, "y": 10, "width": 40, "height": 30,
        })
        await main_module.room_media_video_add("p1", {
            "objectId": tv["objectId"], "videoId": "video-1", "title": "Lesson",
            "youtubeVideoId": "dQw4w9WgXcQ",
        })
        removed = await main_module.room_media_video_remove("p1", {
            "objectId": tv["objectId"], "videoId": "video-1",
        })
        assert removed is True

    async def test_track_add_then_view_playlist_interaction_returns_it(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        player = await main_module.room_object_create("p1", {
            "objectType": "music_player", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        track = await main_module.room_media_track_add("p1", {
            "objectId": player["objectId"], "trackId": "track-1", "title": "Song",
            "youtubeVideoId": "dQw4w9WgXcQ",
        })
        assert track["trackId"] == "track-1"

        result = await main_module.room_object_interact("p1", {
            "objectId": player["objectId"], "interactionType": "view_playlist",
        })
        assert [t["trackId"] for t in result["payload"]["tracks"]] == ["track-1"]

    async def test_track_remove(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        player = await main_module.room_object_create("p1", {
            "objectType": "music_player", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_media_track_add("p1", {
            "objectId": player["objectId"], "trackId": "track-1", "title": "Song",
            "youtubeVideoId": "dQw4w9WgXcQ",
        })
        removed = await main_module.room_media_track_remove("p1", {
            "objectId": player["objectId"], "trackId": "track-1",
        })
        assert removed is True

    async def test_sync_start_join_update_end_flow(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms, "p1")
        await self._join(rooms, "p2")

        tv = await main_module.room_object_create("p1", {
            "objectType": "tv", "x": 10, "y": 10, "width": 40, "height": 30,
        })
        await main_module.room_media_video_add("p1", {
            "objectId": tv["objectId"], "videoId": "video-1", "title": "Lesson",
            "youtubeVideoId": "dQw4w9WgXcQ",
        })

        session = await main_module.room_media_sync_start("p1", {
            "objectId": tv["objectId"], "itemId": "video-1",
        })
        assert session["hostId"] == "p1"

        session = await main_module.room_media_sync_join("p2", {"objectId": tv["objectId"]})
        assert set(session["participants"]) == {"p1", "p2"}

        session = await main_module.room_media_sync_update("p1", {
            "objectId": tv["objectId"], "isPlaying": False, "positionSeconds": 12,
        })
        assert session["isPlaying"] is False
        assert session["positionSeconds"] == 12

        # non-host cannot update playback
        await main_module.room_media_sync_update("p2", {
            "objectId": tv["objectId"], "isPlaying": True, "positionSeconds": 20,
        })
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

        await main_module.room_media_sync_leave("p2", {"objectId": tv["objectId"]})
        ended = await main_module.room_media_sync_end("p1", {"objectId": tv["objectId"]})
        assert ended is True

        broadcasts = [e for e in fake_sio.emitted if e[0] == "room:media:sync:updated"]
        assert broadcasts

    async def test_zone_and_trigger_create_delete(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        zone = await main_module.room_zone_create("p1", {
            "zoneId": "z1", "zoneType": "interaction",
            "minX": 0, "minY": 0, "maxX": 50, "maxY": 50,
        })
        assert zone["zoneId"] == "z1"

        trigger = await main_module.room_trigger_create("p1", {
            "triggerId": "t1", "zoneId": "z1", "eventType": "dialogue", "payload": {"nodeId": "n1"},
        })
        assert trigger["triggerId"] == "t1"

        builder = rooms.get_builder("lobby")
        await main_module.room_trigger_delete("p1", {"triggerId": "t1"})
        await main_module.room_zone_delete("p1", {"zoneId": "z1"})
        assert builder.get_zone("z1") is None

    async def test_version_save_publish_rollback(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        v1 = await main_module.room_version_save("p1", {"snapshot": {"tiles": []}})
        assert v1["versionNumber"] == 1

        published = await main_module.room_version_publish("p1", {"versionNumber": 1})
        assert published["isActive"] is True

        rollback_events_before = len(fake_sio.emitted)
        await main_module.room_version_rollback("p1", {"versionNumber": 1})
        assert len(fake_sio.emitted) > rollback_events_before

    async def test_character_configure_then_talk_returns_start_node(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        npc = await main_module.room_object_create("p1", {
            "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        character = await main_module.room_character_configure("p1", {
            "objectId": npc["objectId"], "name": "Professor Owl", "role": "guide", "startNodeId": "node-1",
        })
        assert character["name"] == "Professor Owl"

        await main_module.room_character_node_add("p1", {
            "objectId": npc["objectId"], "nodeId": "node-1", "characterLine": "Welcome!",
            "choices": [{"text": "Continue", "nextNodeId": "node-2"}],
        })
        await main_module.room_character_node_add("p1", {
            "objectId": npc["objectId"], "nodeId": "node-2", "characterLine": "The end.",
        })

        result = await main_module.room_object_interact("p1", {
            "objectId": npc["objectId"], "interactionType": "talk",
        })
        assert result["payload"]["node"]["nodeId"] == "node-1"
        assert result["payload"]["mode"] == "predefined"

    async def test_character_configure_denied_for_non_owner_non_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms, "p1")
        await self._join(rooms, "p2")

        npc = await main_module.room_object_create("p1", {
            "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_character_configure("p2", {
            "objectId": npc["objectId"], "name": "Owl", "role": "guide", "startNodeId": "node-1",
        })
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

    async def test_character_talk_advances_story_with_choice_index(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        npc = await main_module.room_object_create("p1", {
            "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_character_configure("p1", {
            "objectId": npc["objectId"], "name": "Owl", "role": "guide", "startNodeId": "node-1",
        })
        await main_module.room_character_node_add("p1", {
            "objectId": npc["objectId"], "nodeId": "node-1", "characterLine": "Welcome!",
            "choices": [{"text": "Continue", "nextNodeId": "node-2"}],
        })
        await main_module.room_character_node_add("p1", {
            "objectId": npc["objectId"], "nodeId": "node-2", "characterLine": "The end.",
        })

        await main_module.room_character_talk("p1", {"objectId": npc["objectId"]})
        result = await main_module.room_character_talk("p1", {"objectId": npc["objectId"], "choiceIndex": 0})
        assert result["node"]["nodeId"] == "node-2"

    async def test_character_knowledge_base_and_generative_config_roundtrip(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        # Generative AI settings are restricted to the room admin (Phase I),
        # so this player must be the room host, not just a lobby member.
        room = rooms.create_room(host_id="p1", name="Owl's Room")
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, room["id"])

        npc = await main_module.room_object_create("p1", {
            "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_character_configure("p1", {
            "objectId": npc["objectId"], "name": "Owl", "role": "guide", "startNodeId": "node-1",
        })
        character = await main_module.room_character_knowledge_base_title_set("p1", {
            "objectId": npc["objectId"], "title": "Owl Facts",
        })
        assert character["knowledgeBase"]["title"] == "Owl Facts"

        character = await main_module.room_character_knowledge_base_document_add("p1", {
            "objectId": npc["objectId"], "title": "Habitat", "docType": "text", "content": "Owls are nocturnal.",
        })
        assert character["knowledgeBase"]["documents"][0]["content"] == "Owls are nocturnal."

        character = await main_module.room_character_generative_configure("p1", {
            "objectId": npc["objectId"], "apiBaseUrl": "https://api.example.com", "apiKey": "secret",
        })
        assert character["generativeEnabled"] is True
        assert "apiKey" not in character

    async def test_character_ask_falls_back_to_predefined_when_generative_disabled(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        npc = await main_module.room_object_create("p1", {
            "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_character_configure("p1", {
            "objectId": npc["objectId"], "name": "Owl", "role": "guide", "startNodeId": "node-1",
        })
        result = await main_module.room_character_ask("p1", {
            "objectId": npc["objectId"], "userMessage": "Any hints?",
        })
        assert result["mode"] == "predefined"

    async def test_character_ask_falls_back_when_generative_call_fails(self, isolate_registry, monkeypatch):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)

        npc = await main_module.room_object_create("p1", {
            "objectType": "ai_character", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_character_configure("p1", {
            "objectId": npc["objectId"], "name": "Owl", "role": "guide", "startNodeId": "node-1",
        })
        await main_module.room_character_generative_configure("p1", {
            "objectId": npc["objectId"], "apiBaseUrl": "https://api.example.com", "apiKey": "secret",
        })

        def failing_call(api_base_url, api_key, knowledge_base, user_message):
            raise RuntimeError("upstream API is down")

        monkeypatch.setattr(main_module, "_call_openai_compatible_endpoint", failing_call)

        result = await main_module.room_character_ask("p1", {
            "objectId": npc["objectId"], "userMessage": "Any hints?",
        })
        assert result["mode"] == "predefined"
        assert result["answer"]


    async def test_handlers_require_room_membership(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await main_module.room_tile_clone("ghost", {"direction": "right"})
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

    async def test_builder_request_sends_state_and_versions_to_caller_only(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)
        await main_module.room_object_create("p1", {
            "objectType": "chair", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        await main_module.room_version_save("p1", {"snapshot": {"tiles": []}})

        await main_module.room_builder_request("p1", {})

        state_events = [e for e in fake_sio.emitted if e[0] == "room:builder:state"]
        version_events = [e for e in fake_sio.emitted if e[0] == "room:builder:versions"]
        assert state_events and state_events[-1][2] == "p1"
        assert state_events[-1][1]["objects"], "expected the created object in the requested state"
        assert version_events and version_events[-1][2] == "p1"
        assert version_events[-1][1]["versions"], "expected the saved draft in the requested versions"

    async def test_builder_request_requires_room_membership(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await main_module.room_builder_request("ghost", {})
        errors = [e for e in fake_sio.emitted if e[0] == "error"]
        assert errors

    async def test_builder_request_with_radius_scopes_objects_to_nearby_tiles(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await self._join(rooms)
        builder = rooms.get_builder("lobby")
        builder.add_tile((0, 0), "right")
        await main_module.room_object_create("p1", {
            "objectType": "chair", "x": 10, "y": 10, "width": 20, "height": 20,
        })
        builder.create_object("far-obj", "chair", (1, 0), x=10, y=10, width=20, height=20)

        await main_module.room_builder_request("p1", {"radius": 0})
        radius_zero_objects = self._builder_state_events(fake_sio)[-1][1]["objects"]
        assert {o["objectId"] for o in radius_zero_objects} == {
            o["objectId"] for o in builder.list_objects(tile=(0, 0))
        }

        await main_module.room_builder_request("p1", {})
        full_objects = self._builder_state_events(fake_sio)[-1][1]["objects"]
        assert len(full_objects) == 2


# Captured at import time, before the autouse `isolate_registry` fixture
# monkeypatches `main_module.sio` to a fake for the rest of the test suite.
# `@sio.on(...)` decorators register on this real server object at import
# time, so this is the only reference that reflects actual handler wiring.
_REAL_SIO = main_module.sio

# Every `room:*` / `player:*` event the client emits via `state.socket.emit(...)`
# in client/js/main.js. Keep in sync with that file: a handler missing its
# `@sio.on(...)` decorator (e.g. accidentally deleted during an edit) causes
# the feature to silently do nothing on the client with no server-side error,
# so this list is the regression guard for that failure mode.
CLIENT_EMITTED_EVENTS = [
    "player:action",
    "player:direction",
    "player:move",
    "room:book:add",
    "room:book:progress:save",
    "room:book:remove",
    "room:builder:request",
    "room:character:ask",
    "room:character:configure",
    "room:character:generative:configure",
    "room:character:knowledge_base:document:add",
    "room:character:knowledge_base:document:remove",
    "room:character:knowledge_base:document:reorder",
    "room:character:knowledge_base:document:update",
    "room:character:knowledge_base:title:set",
    "room:character:node:add",
    "room:character:talk",
    "room:create",
    "room:join",
    "room:media:sync:end",
    "room:media:sync:join",
    "room:media:sync:leave",
    "room:media:sync:start",
    "room:media:track:add",
    "room:media:track:remove",
    "room:media:video:add",
    "room:media:video:remove",
    "room:moderation:audit_log:request",
    "room:moderation:ban",
    "room:moderation:external_links:set",
    "room:moderation:kick",
    "room:moderation:mute",
    "room:moderation:report",
    "room:moderation:reports:request",
    "room:moderation:unban",
    "room:moderation:unmute",
    "room:object:create",
    "room:object:delete",
    "room:object:duplicate",
    "room:object:interact",
    "room:object:layer",
    "room:object:lock",
    "room:object:move",
    "room:object:permission",
    "room:object:resize",
    "room:object:rotate",
    "room:role:assign",
    "room:tile:add",
    "room:tile:clone",
    "room:tile:configure",
    "room:tile:delete",
    "room:trigger:create",
    "room:trigger:delete",
    "room:version:publish",
    "room:version:rollback",
    "room:version:save",
    "room:zone:create",
    "room:zone:delete",
]


class TestSocketHandlerRegistration:
    """Regression guard: every event the client emits must have a server-side
    `@sio.on(...)` handler registered, or the feature silently no-ops."""

    @pytest.mark.parametrize("event", CLIENT_EMITTED_EVENTS)
    def test_client_emitted_event_has_registered_handler(self, event):
        registered = _REAL_SIO.handlers.get("/", {})
        assert event in registered, f"no @sio.on handler registered for {event!r}"
