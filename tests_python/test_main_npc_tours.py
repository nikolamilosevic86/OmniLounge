"""TDD tests for the AI-character guided-tour ("follow me") socket handlers
in server/main.py: `room:character:waypoint:add` / `:remove` / `:reorder` /
`:clear`, and `room:character:tour:start` / `:stop`.

The split of concerns under test here is deliberate: authoring a route is a
*build* action and is permission-gated like every other object edit, while
starting a tour is a *learner* action any visitor may take. This file also
covers the game-loop bridge (`tick_guided_tours`) that walks a touring
character and broadcasts its position on `room:npc:moved`.
"""
import pytest

import server.main as main_module
from server.game.avatar import create_default_avatar
from server.game.npc_guide import STATUS_RETURNING, STATUS_WALKING


class FakeSio:
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []

    async def emit(self, event, data=None, room=None, skip_sid=None):
        self.emitted.append((event, data, room))

    async def enter_room(self, sid, room):
        return None

    async def leave_room(self, sid, room):
        return None

    def events_named(self, name):
        return [data for event, data, _room in self.emitted if event == name]


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
        "objectType": "ai_character", "x": 100, "y": 100, "width": 20, "height": 20,
    })
    await main_module.room_character_configure(host_id, {
        "objectId": npc["objectId"], "name": "Owl", "role": "guide", "startNodeId": "node-1",
    })
    return npc["objectId"]


def _error_messages(fake_sio):
    return [data["message"] for event, data, _room in fake_sio.emitted if event == "error"]


class TestWaypointAuthoring:
    async def test_adds_a_waypoint(self, isolate_registry):
        rooms, _ = isolate_registry
        object_id = await _make_character(rooms)

        waypoints = await main_module.room_character_waypoint_add("p1", {
            "objectId": object_id, "waypointId": "wp-1", "x": 200, "y": 220, "label": "The library",
        })

        assert len(waypoints) == 1
        assert waypoints[0]["waypointId"] == "wp-1"
        assert waypoints[0]["label"] == "The library"

    async def test_generates_a_waypoint_id_when_omitted(self, isolate_registry):
        rooms, _ = isolate_registry
        object_id = await _make_character(rooms)

        waypoints = await main_module.room_character_waypoint_add("p1", {
            "objectId": object_id, "x": 200, "y": 220,
        })

        assert waypoints[0]["waypointId"].startswith("wp-")

    async def test_waypoints_appear_on_the_broadcast_object(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        await main_module.room_character_waypoint_add("p1", {
            "objectId": object_id, "waypointId": "wp-1", "x": 200, "y": 220,
        })

        # Visitors who cannot edit the character still need to know it offers
        # a tour, so the route rides along on the object payload.
        states = fake_sio.events_named("room:builder:state")
        objects = states[-1]["objects"]
        character = next(o for o in objects if o["objectId"] == object_id)
        assert [w["waypointId"] for w in character["waypoints"]] == ["wp-1"]
        assert character["tour"] is None

    async def test_denied_for_non_owner_non_host(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        rooms.join_room("p2", create_default_avatar("Bob"), "lobby")

        result = await main_module.room_character_waypoint_add("p2", {
            "objectId": object_id, "waypointId": "wp-1", "x": 200, "y": 220,
        })

        assert result is None
        assert _error_messages(fake_sio)

    async def test_requires_joining_a_room_first(self, isolate_registry):
        _rooms, fake_sio = isolate_registry

        result = await main_module.room_character_waypoint_add("ghost", {"objectId": "x", "x": 1, "y": 1})

        assert result is None
        assert "Join a room first" in _error_messages(fake_sio)

    async def test_rejects_waypoints_on_a_non_character_object(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        rooms.join_room("p1", create_default_avatar("Alice"), "lobby")
        obj = await main_module.room_object_create("p1", {
            "objectType": "table", "x": 10, "y": 10, "width": 20, "height": 20,
        })

        result = await main_module.room_character_waypoint_add("p1", {
            "objectId": obj["objectId"], "x": 200, "y": 220,
        })

        assert result is None
        assert _error_messages(fake_sio)

    async def test_removes_a_waypoint(self, isolate_registry):
        rooms, _ = isolate_registry
        object_id = await _make_character(rooms)
        await main_module.room_character_waypoint_add("p1", {"objectId": object_id, "waypointId": "wp-1", "x": 200, "y": 220})
        await main_module.room_character_waypoint_add("p1", {"objectId": object_id, "waypointId": "wp-2", "x": 300, "y": 220})

        waypoints = await main_module.room_character_waypoint_remove("p1", {
            "objectId": object_id, "waypointId": "wp-1",
        })

        assert [w["waypointId"] for w in waypoints] == ["wp-2"]

    async def test_reorders_a_waypoint(self, isolate_registry):
        rooms, _ = isolate_registry
        object_id = await _make_character(rooms)
        await main_module.room_character_waypoint_add("p1", {"objectId": object_id, "waypointId": "wp-1", "x": 200, "y": 220})
        await main_module.room_character_waypoint_add("p1", {"objectId": object_id, "waypointId": "wp-2", "x": 300, "y": 220})

        waypoints = await main_module.room_character_waypoint_reorder("p1", {
            "objectId": object_id, "waypointId": "wp-2", "direction": "up",
        })

        assert [w["waypointId"] for w in waypoints] == ["wp-2", "wp-1"]

    async def test_reorder_rejects_a_bad_direction(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)
        await main_module.room_character_waypoint_add("p1", {"objectId": object_id, "waypointId": "wp-1", "x": 200, "y": 220})

        result = await main_module.room_character_waypoint_reorder("p1", {
            "objectId": object_id, "waypointId": "wp-1", "direction": "sideways",
        })

        assert result is None
        assert _error_messages(fake_sio)

    async def test_clears_all_waypoints(self, isolate_registry):
        rooms, _ = isolate_registry
        object_id = await _make_character(rooms)
        await main_module.room_character_waypoint_add("p1", {"objectId": object_id, "waypointId": "wp-1", "x": 200, "y": 220})

        assert await main_module.room_character_waypoint_clear("p1", {"objectId": object_id}) == []

    async def test_deleting_the_character_discards_its_route(self, isolate_registry):
        rooms, _ = isolate_registry
        object_id = await _make_character(rooms)
        await main_module.room_character_waypoint_add("p1", {"objectId": object_id, "waypointId": "wp-1", "x": 200, "y": 220})
        builder = rooms.get_builder("lobby")

        await main_module.room_object_delete("p1", {"objectId": object_id})

        # A recycled object id must not inherit the deleted character's tour.
        assert builder._guide.list_waypoints(object_id) == []


class TestTourLifecycle:
    async def _character_with_route(self, rooms):
        object_id = await _make_character(rooms)
        await main_module.room_character_waypoint_add("p1", {
            "objectId": object_id, "waypointId": "wp-1", "x": 300, "y": 100, "label": "The library",
        })
        return object_id

    async def test_any_visitor_can_start_a_tour(self, isolate_registry):
        rooms, _ = isolate_registry
        object_id = await self._character_with_route(rooms)
        rooms.join_room("p2", create_default_avatar("Bob"), "lobby")

        tour = await main_module.room_character_tour_start("p2", {"objectId": object_id})

        # Following a guide is a learner action, not an authoring one, so it
        # is deliberately not permission-gated.
        assert tour["status"] == STATUS_WALKING
        assert tour["followers"] == ["p2"]

    async def test_cannot_start_a_tour_without_a_route(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await _make_character(rooms)

        result = await main_module.room_character_tour_start("p1", {"objectId": object_id})

        assert result is None
        assert any("no tour route" in m for m in _error_messages(fake_sio))

    async def test_stopping_the_tour_sends_the_character_home(self, isolate_registry):
        rooms, _ = isolate_registry
        object_id = await self._character_with_route(rooms)
        await main_module.room_character_tour_start("p1", {"objectId": object_id})

        tour = await main_module.room_character_tour_stop("p1", {"objectId": object_id})

        assert tour["status"] == STATUS_RETURNING

    async def test_tour_start_requires_a_room(self, isolate_registry):
        _rooms, fake_sio = isolate_registry

        assert await main_module.room_character_tour_start("ghost", {"objectId": "x"}) is None
        assert "Join a room first" in _error_messages(fake_sio)


class TestGuidedTourTick:
    async def _touring_character(self, rooms):
        object_id = await _make_character(rooms)
        await main_module.room_character_waypoint_add("p1", {
            "objectId": object_id, "waypointId": "wp-1", "x": 400, "y": 100, "label": "The library",
        })
        await main_module.room_character_tour_start("p1", {"objectId": object_id})
        return object_id

    async def test_tick_moves_the_character_and_broadcasts(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await self._touring_character(rooms)

        await main_module.tick_guided_tours("lobby", now_ms=1000.0)

        moves = fake_sio.events_named("room:npc:moved")
        assert len(moves) == 1
        assert moves[0]["objectId"] == object_id
        assert moves[0]["position"]["x"] > 100

    async def test_tick_writes_the_new_position_onto_the_object(self, isolate_registry):
        rooms, _ = isolate_registry
        object_id = await self._touring_character(rooms)
        builder = rooms.get_builder("lobby")

        await main_module.tick_guided_tours("lobby", now_ms=1000.0)

        # The position must live on the object itself, not only in the guide
        # engine, so collision and hit-testing see the character where it is.
        assert builder.get_object(object_id)["x"] > 100

    async def test_tick_is_a_noop_when_nothing_is_touring(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        await _make_character(rooms)

        await main_module.tick_guided_tours("lobby", now_ms=1000.0)

        assert fake_sio.events_named("room:npc:moved") == []

    async def test_tick_ignores_unknown_rooms(self, isolate_registry):
        _rooms, fake_sio = isolate_registry

        await main_module.tick_guided_tours("no-such-room", now_ms=1000.0)

        assert fake_sio.events_named("room:npc:moved") == []

    async def test_character_speaks_the_waypoint_label_on_arrival(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        object_id = await self._touring_character(rooms)

        now = 0.0
        for _ in range(400):
            now += 33.0
            await main_module.tick_guided_tours("lobby", now_ms=now)
            if fake_sio.events_named("room:npc:say"):
                break

        says = fake_sio.events_named("room:npc:say")
        assert says, "character never announced its waypoint"
        assert says[0]["objectId"] == object_id
        assert says[0]["text"] == "The library"

    async def test_a_broken_tour_does_not_break_the_game_loop(self, isolate_registry, monkeypatch):
        rooms, fake_sio = isolate_registry
        await self._touring_character(rooms)
        builder = rooms.get_builder("lobby")

        def explode(_now_ms):
            raise RuntimeError("boom")

        monkeypatch.setattr(builder, "tick_character_tours", explode)

        # The game loop ticks every room every frame; one bad tour must not
        # take movement down for the whole server.
        await main_module.tick_guided_tours("lobby", now_ms=1000.0)

        assert fake_sio.events_named("room:npc:moved") == []
