from server.game.avatar import create_default_avatar
from server.game.rooms_registry import RoomsRegistry


class TestRoomsRegistryTiles:
    def test_room_starts_with_origin_tile(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Geo Room")
        tiles = registry.get_room_tiles(room["id"])
        assert tiles == [{"x": 0, "y": 0}]

    def test_add_neighbor_tile_updates_tile_set(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Geo Room")
        created = registry.add_neighbor_tile(room["id"], (0, 0), "right")
        assert created == {"x": 1, "y": 0}
        assert {"x": 1, "y": 0} in registry.get_room_tiles(room["id"])

    def test_transition_player_tile_only_when_neighbor_exists(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Geo Room")
        avatar = create_default_avatar("Alice")
        registry.join_room("p1", avatar, room["id"])

        no_transition = registry.transition_player_tile_if_needed(
            "p1",
            room["id"],
            {"x": 799.0, "y": 300.0},
        )
        assert no_transition is None
        assert registry.get_player_tile("p1") == (0, 0)

        registry.add_neighbor_tile(room["id"], (0, 0), "right")
        transition = registry.transition_player_tile_if_needed(
            "p1",
            room["id"],
            {"x": 799.0, "y": 300.0},
        )
        assert transition is not None
        assert transition["tile"] == {"x": 1, "y": 0}
        assert registry.get_player_tile("p1") == (1, 0)

    def test_transition_out_of_bounds_is_ignored(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Geo Room")
        avatar = create_default_avatar("Alice")
        player = registry.join_room("p1", avatar, room["id"])
        assert player is not None

        registry.player_tile["p1"] = (2, 0)
        transition = registry.transition_player_tile_if_needed(
            "p1",
            room["id"],
            {"x": 799.0, "y": 300.0},
        )
        assert transition is None
        assert registry.get_player_tile("p1") == (2, 0)

    def test_warp_player_to_tile_moves_to_a_non_adjacent_existing_tile(self):
        # design doc feature_designs/escape_room_feature_design.md §8.3: an
        # escape_door's destinationTile is a direct (non-edge-adjacent) jump,
        # unlike transition_player_tile_if_needed which only ever crosses to
        # a neighboring tile.
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Geo Room")
        avatar = create_default_avatar("Alice")
        registry.join_room("p1", avatar, room["id"])
        registry.add_neighbor_tile(room["id"], (0, 0), "right")
        registry.add_neighbor_tile(room["id"], (1, 0), "right")

        result = registry.warp_player_to_tile("p1", room["id"], (2, 0))

        assert result is not None
        assert result["tile"] == {"x": 2, "y": 0}
        assert registry.get_player_tile("p1") == (2, 0)

    def test_warp_player_to_tile_returns_none_for_nonexistent_tile(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Geo Room")
        avatar = create_default_avatar("Alice")
        registry.join_room("p1", avatar, room["id"])

        result = registry.warp_player_to_tile("p1", room["id"], (1, 0))

        assert result is None
        assert registry.get_player_tile("p1") == (0, 0)

    def test_warp_player_to_tile_returns_a_default_arrival_position(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Geo Room")
        avatar = create_default_avatar("Alice")
        registry.join_room("p1", avatar, room["id"])
        registry.add_neighbor_tile(room["id"], (0, 0), "right")

        result = registry.warp_player_to_tile("p1", room["id"], (1, 0))

        assert result["position"] == {"x": 400.0, "y": 300.0}

