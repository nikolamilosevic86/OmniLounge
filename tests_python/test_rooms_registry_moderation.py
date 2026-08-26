import pytest

from server.game.moderation import ROLE_MODERATOR
from server.game.rooms_registry import RoomsRegistry


class TestRoomsRegistryModeration:
    def test_new_room_has_moderation_state(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Edu Room")
        moderation = registry.get_moderation(room["id"])
        assert moderation is not None
        assert moderation.get_role("h1") == "owner"

    def test_lobby_has_moderation_state(self):
        registry = RoomsRegistry()
        assert registry.get_moderation("lobby") is not None

    def test_unknown_room_moderation_is_none(self):
        registry = RoomsRegistry()
        assert registry.get_moderation("does-not-exist") is None

    def test_banned_player_cannot_join_room(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Edu Room")
        moderation = registry.get_moderation(room["id"])
        moderation.assign_role("mod1", ROLE_MODERATOR, actor_id="h1")
        moderation.ban("carol", actor_id="mod1")

        error = registry.get_room_join_error("carol", room["id"])
        assert error == "banned"

    def test_non_banned_player_can_join_room(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Edu Room")
        error = registry.get_room_join_error("carol", room["id"])
        assert error is None
