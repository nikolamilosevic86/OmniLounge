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
    """Give each test a clean rooms registry and a fake sio so no real
    network/db access happens, and tests don't leak player state."""
    from server.game.rooms_registry import RoomsRegistry

    fresh_rooms = RoomsRegistry()
    monkeypatch.setattr(main_module, "rooms", fresh_rooms)

    fake_sio = FakeSio()
    monkeypatch.setattr(main_module, "sio", fake_sio)

    return fresh_rooms, fake_sio


class TestPlayerMoveHandlesMalformedInput:
    """A raw/malicious socket client can send any JSON payload for
    player:move; the handler must not raise on missing or non-numeric
    x/y instead of trusting the client to always send well-formed data."""

    async def test_player_move_with_valid_coordinates_still_works(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_move("p1", {"x": 100, "y": 150})

        moving_events = [e for e in fake_sio.emitted if e[0] == "player:moving"]
        assert moving_events
        assert moving_events[-1][1]["targetPosition"]["x"] == 100

    async def test_player_move_with_missing_x_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_move("p1", {"y": 150})

    async def test_player_move_with_missing_data_keys_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_move("p1", {})

    async def test_player_move_with_non_numeric_coordinates_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_move("p1", {"x": "not-a-number", "y": "also-not"})


class TestPlayerActionHandlesMalformedTarget:
    """Both the teleport and walk-to-target branches of player:action
    forward `target` into clamp_position(); malformed target dicts must
    not crash the handler."""

    async def test_player_action_teleport_with_malformed_target_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_action("p1", {"teleport": True, "target": {"foo": "bar"}})

    async def test_player_action_walk_to_target_with_malformed_target_does_not_raise(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_action("p1", {"target": {"x": "nope"}})

    async def test_player_action_teleport_with_valid_target_still_works(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_action("p1", {"teleport": True, "target": {"x": 200, "y": 250}})

        room = rooms.get_room("lobby")
        player = room.get_player("p1")
        assert player["position"]["x"] == 200


class TestPlayerDirectionRejectsMalformedInput:
    """`player:direction` stores its payload verbatim on the player's
    `direction` field with no validation. That field is read every single
    game-loop tick (server/main.py `apply_player_movement` ->
    `move_by_direction`, which computes `dx * dx`) for EVERY player in
    EVERY room -- unlike player:move/player:action, a bad value here isn't
    just mishandled for one request, it raises inside the single shared
    `game_loop()` asyncio task on the very next tick, silently killing
    movement/AI processing server-wide until restart (game_loop has no
    try/except and nothing restarts it)."""

    async def test_player_direction_with_valid_numbers_still_works(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_direction("p1", {"x": 1, "y": 0})

        room = rooms.get_room("lobby")
        assert room.get_player("p1")["direction"] == {"x": 1, "y": 0}

    async def test_player_direction_with_non_numeric_x_does_not_corrupt_state(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_direction("p1", {"x": "boom", "y": 0})

        room = rooms.get_room("lobby")
        player = room.get_player("p1")
        # Malformed input must be ignored, not stored -- otherwise the next
        # game_loop tick crashes computing dx * dx on a non-numeric value.
        assert player["direction"] == {"x": 0, "y": 0}

    async def test_player_direction_with_non_numeric_input_does_not_crash_next_game_tick(self, isolate_registry):
        """Reproduces the real-world crash: send a malformed direction
        through the handler exactly as a client would, then run the same
        movement computation the game loop runs every tick."""
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")

        await main_module.player_direction("p1", {"x": "boom", "y": 0})

        room = rooms.get_room("lobby")
        player = room.get_player("p1")
        # Must not raise -- this is exactly what game_loop() does every tick.
        main_module.apply_player_movement(room, "lobby", player, now_ms=0)


class TestTileTransitionEndToEnd:
    """Reproduces the reported real-world flow: a builder adds a neighbor
    tile, then a player walks straight toward that edge using only a single
    direction key (as opposed to hand-crafting an already-at-the-edge
    position, which the older unit tests did). This must actually land the
    player in the new tile, at the far edge of it, exactly like clicking
    "Add Up" and holding the up arrow key in the real client."""

    def _run_until_transition_or_timeout(self, room, player, *, max_ticks=300):
        for _ in range(max_ticks):
            main_module.apply_player_movement(room, "lobby", player, now_ms=0)
            if player["tile"] != {"x": 0, "y": 0}:
                return True
        return False

    def test_walking_up_reaches_newly_added_top_tile(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")
        room = rooms.get_room("lobby")
        player = room.get_player("p1")

        # Start in a furniture-free column so this test isolates the tile
        # transition itself (the separate wall-slide behavior for players
        # who spawn directly under furniture is covered below).
        player["position"] = {"x": 500.0, "y": 300.0}
        rooms.add_neighbor_tile("lobby", (0, 0), "top")

        player["direction"] = {"x": 0, "y": -1}
        transitioned = self._run_until_transition_or_timeout(room, player)

        assert transitioned
        assert player["tile"] == {"x": 0, "y": -1}
        # Lands near the bottom of the new tile, matching the reported
        # expectation ("character should be at the bottom of next tile").
        from server.game.movement import ROOM_BOUNDS
        from server.game.tile_navigation import TRANSITION_INSET

        assert player["position"]["y"] == pytest.approx(ROOM_BOUNDS["height"] - TRANSITION_INSET)

    def test_walking_up_from_every_realistic_spawn_reaches_new_tile(self, isolate_registry):
        """Regression test for players getting permanently stuck against the
        lobby's hardcoded furniture (sofas/table/dj-deck) when holding a
        single direction key, unable to ever reach the tile edge. Exercises
        many realistic spawn points -- some of which land directly below/
        beside furniture -- to make sure every one of them can still reach
        the newly added tile by holding "up", not just a hand-picked clear
        column."""
        rooms, _fake_sio = isolate_registry
        rooms.add_neighbor_tile("lobby", (0, 0), "top")
        room = rooms.get_room("lobby")

        for i in range(20):
            avatar = create_default_avatar(f"Player{i}")
            player = room.add_player(f"p{i}", avatar)
            rooms.player_tile[f"p{i}"] = (0, 0)
            player["tile"] = {"x": 0, "y": 0}
            player["direction"] = {"x": 0, "y": -1}

            transitioned = self._run_until_transition_or_timeout(room, player)

            assert transitioned, f"player spawned at {player['position']} got stuck"
            assert player["tile"] == {"x": 0, "y": -1}


class TestPlacingObjectOnPlayerDoesNotTrapThem:
    """Reproduces the reported real-world flow exactly: a player opens the
    build panel and clicks "Add Object" (client sends the player's OWN
    current position as the new object's x/y, which the server stores
    verbatim as the object's top-left corner -- so the player ends up
    standing right at the corner of/inside the brand-new object's hitbox)
    and must still be able to walk away afterward, for every placeable
    object type, not just the hardcoded lobby furniture."""

    @pytest.mark.parametrize("object_type", ["bookshelf", "table", "chair", "sofa", "bar", "tv", "music_player"])
    async def test_can_walk_away_after_placing_object_on_self(self, isolate_registry, object_type):
        rooms, fake_sio = isolate_registry
        avatar = create_default_avatar("Alice")
        rooms.join_room("p1", avatar, "lobby")
        room = rooms.get_room("lobby")
        player = room.get_player("p1")

        # Furniture-free spot so this test isolates the embedded-object
        # escape behavior from the separate wall-slide-around-furniture
        # behavior covered elsewhere.
        player["position"] = {"x": 400.0, "y": 300.0}

        await main_module.room_object_create(
            "p1",
            {
                "objectType": object_type,
                "x": player["position"]["x"],
                "y": player["position"]["y"],
            },
        )

        player["direction"] = {"x": 1, "y": 0}
        for _ in range(80):
            main_module.apply_player_movement(room, "lobby", player, now_ms=0)

        assert player["position"]["x"] > 400.0, (
            f"player got stuck after a {object_type} was placed on top of them"
        )


class TestTileTransitionBroadcastsUpdatedTile:
    """The client plays its directional "swoosh" wipe by diffing the `tile`
    field across consecutive `room:state` broadcasts, so the whole feature
    only works if a transition actually reaches the wire. Drives the real
    `room:tile:add` socket handler (as clicking "Add Up" does) rather than
    poking the registry directly."""

    async def test_walking_into_a_newly_added_tile_broadcasts_the_new_tile(self, isolate_registry):
        rooms, fake_sio = isolate_registry
        rooms.join_room("p1", create_default_avatar("Alice"), "lobby")
        room = rooms.get_room("lobby")
        player = room.get_player("p1")
        player["position"] = {"x": 500.0, "y": 300.0}

        await main_module.room_tile_add("p1", {"direction": "top"})
        assert [e for e in fake_sio.emitted if e[0] == "room:tiles"], "tile was never added"

        player["direction"] = {"x": 0, "y": -1}
        for _ in range(300):
            main_module.apply_player_movement(room, "lobby", player, now_ms=0)
            if player["tile"] != {"x": 0, "y": 0}:
                break

        assert player["tile"] == {"x": 0, "y": -1}

        await main_module.broadcast_room_state("lobby")
        states = [e for e in fake_sio.emitted if e[0] == "room:state"]
        assert states, "no room:state broadcast reached the client"
        me = next(p for p in states[-1][1]["players"] if p["id"] == "p1")
        assert me["tile"] == {"x": 0, "y": -1}, (
            "room:state omitted the updated tile, so the client can never "
            "detect the transition and play the swoosh animation"
        )


class TestEscapeDoorCollisionIsPerVisitor:
    """server/main.py: `_tile_collision_obstacles` gains a `requester_id`
    param (design doc feature_designs/escape_room_feature_design.md §5.1)
    and skips only `escape_door` objects that specific player has personally
    opened -- an escape_door blocks movement like any other object until the
    requesting player opens it, and keeps blocking every other player who
    hasn't opened it themselves."""

    async def test_unopened_escape_door_blocks_movement(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        rooms.join_room("p1", create_default_avatar("Alice"), "lobby")
        room = rooms.get_room("lobby")
        player = room.get_player("p1")
        player["position"] = {"x": 300.0, "y": 300.0}

        builder = rooms.get_builder("lobby")
        # A full room-height wall segment, matching how an escape_door
        # would realistically be sized to seal off a tile edge -- a small
        # box would just trigger the existing anti-stuck wall-slide-around
        # behavior (see TestTileTransitionEndToEnd) instead of testing that
        # the door itself blocks the player.
        builder.create_object("door-1", "escape_door", (0, 0), x=340.0, y=20.0, width=40.0, height=560.0)

        player["direction"] = {"x": 1, "y": 0}
        for _ in range(20):
            main_module.apply_player_movement(room, "lobby", player, now_ms=0)

        assert player["position"]["x"] < 340.0

    async def test_escape_door_opened_by_this_player_no_longer_blocks_them(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        rooms.join_room("p1", create_default_avatar("Alice"), "lobby")
        room = rooms.get_room("lobby")
        player = room.get_player("p1")
        player["position"] = {"x": 300.0, "y": 300.0}

        builder = rooms.get_builder("lobby")
        builder.create_object("door-1", "escape_door", (0, 0), x=340.0, y=20.0, width=40.0, height=560.0)
        builder.interact_with_object("door-1", "attempt_open", requester_id="p1", now_ms=0)

        player["direction"] = {"x": 1, "y": 0}
        for _ in range(80):
            main_module.apply_player_movement(room, "lobby", player, now_ms=0)

        assert player["position"]["x"] > 400.0

    async def test_escape_door_opened_by_another_player_still_blocks_this_one(self, isolate_registry):
        rooms, _fake_sio = isolate_registry
        rooms.join_room("p1", create_default_avatar("Alice"), "lobby")
        rooms.join_room("p2", create_default_avatar("Bob"), "lobby")
        room = rooms.get_room("lobby")
        p2 = room.get_player("p2")
        p2["position"] = {"x": 300.0, "y": 300.0}

        builder = rooms.get_builder("lobby")
        builder.create_object("door-1", "escape_door", (0, 0), x=340.0, y=20.0, width=40.0, height=560.0)
        builder.interact_with_object("door-1", "attempt_open", requester_id="p1", now_ms=0)

        p2["direction"] = {"x": 1, "y": 0}
        for _ in range(20):
            main_module.apply_player_movement(room, "lobby", p2, now_ms=0)

        assert p2["position"]["x"] < 340.0
