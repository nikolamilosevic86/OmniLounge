from server.game.rooms_registry import RoomsRegistry


class TestRoomsRegistryBuilder:
    def test_new_room_has_builder_state(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Edu Room")
        builder = registry.get_builder(room["id"])
        assert builder is not None
        assert builder.list_tiles() == [
            {"x": 0, "y": 0, "label": None, "purposeTag": None,
             "backgroundStyle": None, "ambianceStyle": None, "isSpawn": True}
        ]

    def test_lobby_has_builder_state(self):
        registry = RoomsRegistry()
        assert registry.get_builder("lobby") is not None

    def test_unknown_room_builder_is_none(self):
        registry = RoomsRegistry()
        assert registry.get_builder("does-not-exist") is None

    def test_add_neighbor_tile_keeps_navigation_and_builder_in_sync(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Edu Room")
        created = registry.add_neighbor_tile(room["id"], (0, 0), "right")
        assert created == {"x": 1, "y": 0}
        builder = registry.get_builder(room["id"])
        assert builder.get_tile((1, 0)) is not None
        assert {"x": 1, "y": 0} in registry.get_room_tiles(room["id"])

    def test_builder_clone_tile_also_registers_navigation_tile(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Edu Room")
        registry.configure_tile(room["id"], (0, 0), label="Lobby")
        cloned = registry.clone_tile(room["id"], (0, 0), "right")
        assert cloned == {"x": 1, "y": 0}
        assert {"x": 1, "y": 0} in registry.get_room_tiles(room["id"])
        assert registry.get_builder(room["id"]).get_tile((1, 0))["label"] == "Lobby"

    def test_builder_delete_tile_also_removes_navigation_tile(self):
        registry = RoomsRegistry()
        room = registry.create_room(host_id="h1", name="Edu Room")
        registry.add_neighbor_tile(room["id"], (0, 0), "right")
        assert registry.delete_tile(room["id"], (1, 0)) is True
        assert {"x": 1, "y": 0} not in registry.get_room_tiles(room["id"])
