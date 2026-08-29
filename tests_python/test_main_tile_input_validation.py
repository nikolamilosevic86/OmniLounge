"""TDD regression tests: room:tile:delete / room:tile:configure crashed when
the client-supplied x/y coordinate was an unhashable JSON type (list/dict).

Both handlers build `coord = (data.get("x", 0), data.get("y", 0))` and pass
it straight to RoomsRegistry.delete_tile/configure_tile ->
RoomBuilderState.delete_tile/configure_tile, which do `self._tiles.get(coord)`.
A tuple containing an unhashable element (e.g. `(["x"], 0)`) raises an
uncaught `TypeError: unhashable type` on that dict lookup -- neither handler
validated x/y type before building the coordinate tuple.
"""
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
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)

    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    return fresh_rooms, fake_sio


async def _join(rooms, player_id="p1"):
    avatar = create_default_avatar("Alice")
    rooms.join_room(player_id, avatar, "lobby")


async def _join_as_host(rooms, player_id="p1"):
    """Tile management is host-only and the shared lobby's host is the
    sentinel "system", so happy-path tile edits need an owned room."""
    room = rooms.create_room(host_id=player_id, name="Host Room")
    rooms.join_room(player_id, create_default_avatar("Alice"), room["id"])
    return room["id"]


class TestRoomTileDeleteRejectsUnhashableCoordinates:
    async def test_delete_with_valid_coordinates_still_works(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = await _join_as_host(rooms)
        rooms.add_neighbor_tile(room_id, (0, 0), "right")

        await main_module.room_tile_delete("p1", {"x": 1, "y": 0})

        builder = rooms.get_builder(room_id)
        assert builder.get_tile((1, 0)) is None

    async def test_delete_with_list_x_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        await main_module.room_tile_delete("p1", {"x": ["not", "hashable"], "y": 0})

    async def test_delete_with_dict_y_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        await main_module.room_tile_delete("p1", {"x": 0, "y": {"nested": "dict"}})


class TestRoomTileConfigureRejectsUnhashableCoordinates:
    async def test_configure_with_valid_coordinates_still_works(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        room_id = await _join_as_host(rooms)

        await main_module.room_tile_configure("p1", {"x": 0, "y": 0, "label": "Entrance"})

        builder = rooms.get_builder(room_id)
        assert builder.get_tile((0, 0))["label"] == "Entrance"

    async def test_configure_with_list_x_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        await main_module.room_tile_configure("p1", {"x": ["not", "hashable"], "y": 0, "label": "x"})

    async def test_configure_with_dict_y_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _join(rooms)

        await main_module.room_tile_configure("p1", {"x": 0, "y": {"nested": "dict"}, "label": "x"})
