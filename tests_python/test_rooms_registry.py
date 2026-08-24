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
