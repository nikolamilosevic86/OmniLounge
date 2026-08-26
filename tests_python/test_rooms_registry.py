from server.game.avatar import create_default_avatar
from server.game.rooms_registry import RoomsRegistry


class TestRoomsRegistry:
    def test_has_default_lobby(self):
        registry = RoomsRegistry()
        rooms = registry.list_rooms()
        lobby = next((r for r in rooms if r["id"] == "lobby"), None)
        assert lobby is not None
        assert lobby["name"] == "Lobby"
        assert lobby["activeUsers"] == 0

    def test_create_room_sets_metadata(self):
        registry = RoomsRegistry()
        room = registry.create_room(
            host_id="host-1",
            name="History Lab",
            topic_tags=["history", "museum"],
            access="public",
            max_users=25,
        )
        assert room["id"].startswith("room-")
        assert room["name"] == "History Lab"
        assert room["hostId"] == "host-1"
        assert room["topicTags"] == ["history", "museum"]
        assert room["access"] == "public"
        assert room["maxUsers"] == 25
        assert room["activeUsers"] == 0

    def test_get_room_host_id_returns_creator(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="host-1", name="History Lab")
        assert registry.get_room_host_id(room["id"]) == "host-1"
        assert registry.get_room_host_id("lobby") == "system"
        assert registry.get_room_host_id("unknown-room") is None

    def test_created_room_has_a_host_token_not_exposed_in_summary(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="host-1", name="History Lab")
        token = registry.get_room_host_token(room["id"])
        assert token
        assert "hostToken" not in room
        assert "hostToken" not in registry.get_room_summary(room["id"])
        assert all("hostToken" not in r for r in registry.list_rooms())

    def test_host_tokens_are_unique_per_room(self):
        registry = RoomsRegistry()
        room_a = registry.create_room(host_id="host-1", name="Room A")
        room_b = registry.create_room(host_id="host-2", name="Room B")
        assert registry.get_room_host_token(room_a["id"]) != registry.get_room_host_token(room_b["id"])

    def test_lobby_has_no_host_token(self):
        registry = RoomsRegistry()
        assert registry.get_room_host_token("lobby") is None


class TestReclaimHost:
    def test_reclaim_host_with_correct_token_transfers_ownership_to_new_id(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="host-1", name="History Lab")
        token = registry.get_room_host_token(room["id"])

        reclaimed = registry.reclaim_host(room["id"], "host-1-new-sid", token)

        assert reclaimed is True
        assert registry.get_room_host_id(room["id"]) == "host-1-new-sid"

    def test_reclaim_host_updates_moderation_owner_so_old_owner_permissions_move(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="host-1", name="History Lab")
        token = registry.get_room_host_token(room["id"])

        registry.reclaim_host(room["id"], "host-1-new-sid", token)

        moderation = registry.get_moderation(room["id"])
        assert moderation.get_role("host-1-new-sid") == "owner"
        assert moderation.get_role("host-1") == "participant"

    def test_reclaim_host_rejects_wrong_token(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="host-1", name="History Lab")

        reclaimed = registry.reclaim_host(room["id"], "attacker-sid", "not-the-real-token")

        assert reclaimed is False
        assert registry.get_room_host_id(room["id"]) == "host-1"

    def test_reclaim_host_rejects_none_token(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="host-1", name="History Lab")

        assert registry.reclaim_host(room["id"], "attacker-sid", None) is False

    def test_reclaim_host_returns_false_for_unknown_room(self):
        registry = RoomsRegistry()
        assert registry.reclaim_host("unknown-room", "someone", "any-token") is False

    def test_join_room_moves_player_and_updates_counts(self):
        registry = RoomsRegistry()
        avatar = create_default_avatar("Alice")
        room = registry.create_room(
            host_id="host-1",
            name="Science Hub",
            topic_tags=["science"],
            access="public",
            max_users=20,
        )

        player = registry.join_room(
            player_id="p1",
            avatar=avatar,
            room_id="lobby",
        )
        assert player is not None
        assert registry.get_player_room_id("p1") == "lobby"

        player = registry.join_room(
            player_id="p1",
            avatar=avatar,
            room_id=room["id"],
        )
        assert player is not None
        assert registry.get_player_room_id("p1") == room["id"]

        rooms = {r["id"]: r for r in registry.list_rooms()}
        assert rooms["lobby"]["activeUsers"] == 0
        assert rooms[room["id"]]["activeUsers"] == 1

    def test_leave_current_room_removes_membership(self):
        registry = RoomsRegistry()
        avatar = create_default_avatar("Bob")
        registry.join_room("p2", avatar, "lobby")
        registry.leave_current_room("p2")
        assert registry.get_player_room_id("p2") is None
        rooms = {r["id"]: r for r in registry.list_rooms()}
        assert rooms["lobby"]["activeUsers"] == 0

    def test_list_rooms_filters_by_topic_and_access(self):
        registry = RoomsRegistry()
        registry.create_room(
            host_id="host-1",
            name="History Hall",
            topic_tags=["history"],
            access="public",
            max_users=20,
        )
        registry.create_room(
            host_id="host-2",
            name="Private Science",
            topic_tags=["science"],
            access="invite",
            max_users=20,
            invite_code="science-42",
        )

        history_rooms = registry.list_rooms(topic="history")
        assert len(history_rooms) == 1
        assert history_rooms[0]["name"] == "History Hall"

        invite_rooms = registry.list_rooms(access="invite")
        assert len(invite_rooms) == 1
        assert invite_rooms[0]["name"] == "Private Science"

    def test_join_room_rejects_when_full(self):
        registry = RoomsRegistry()
        room = registry.create_room(
            host_id="host-1",
            name="Small Group",
            topic_tags=["math"],
            access="public",
            max_users=1,
        )

        first_avatar = create_default_avatar("Alice")
        second_avatar = create_default_avatar("Bob")

        assert registry.join_room("p1", first_avatar, room["id"]) is not None
        assert registry.join_room("p2", second_avatar, room["id"]) is None

    def test_join_room_requires_invite_code_for_invite_rooms(self):
        registry = RoomsRegistry()
        room = registry.create_room(
            host_id="host-1",
            name="Invite Only",
            topic_tags=["language"],
            access="invite",
            max_users=10,
            invite_code="open-sesame",
        )
        avatar = create_default_avatar("Guest")

        assert registry.join_room("p1", avatar, room["id"]) is None
        assert registry.join_room("p1", avatar, room["id"], invite_code="open-sesame") is not None
