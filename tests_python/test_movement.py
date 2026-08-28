from server.game.movement import (
    OBSTACLES,
    ROOM_BOUNDS,
    calculate_distance,
    clamp_position,
    collides_with_obstacle,
    create_position,
    is_within_bounds,
    move_by_direction,
    move_toward,
    resolve_collision,
)


class TestMovement:
    def test_create_position_defaults(self):
        pos = create_position()
        assert pos["x"] == ROOM_BOUNDS["width"] / 2

    def test_move_toward(self):
        current = create_position(0, 0)
        target = {"x": 100, "y": 0}
        result = move_toward(current, target, 10)
        assert result["x"] == 10

    def test_move_by_direction(self):
        current = create_position(100, 100)
        result = move_by_direction(current, {"x": 0, "y": -1}, 5)
        assert result["y"] == 95

    def test_clamp_position(self):
        clamped = clamp_position({"x": -10, "y": 9999})
        assert clamped["x"] >= ROOM_BOUNDS["minX"]
        assert clamped["y"] <= ROOM_BOUNDS["maxY"]

    def test_is_within_bounds(self):
        assert is_within_bounds(create_position(400, 300)) is True
        assert is_within_bounds({"x": -1, "y": 300}) is False

    def test_calculate_distance(self):
        assert calculate_distance({"x": 0, "y": 0}, {"x": 3, "y": 4}) == 5


CUSTOM_OBSTACLE = {"id": "builder-object", "x": 100.0, "y": 100.0, "w": 40.0, "h": 40.0}


class TestExtraObstacles:
    """Builder-placed room objects must block movement the same way the
    hardcoded lobby OBSTACLES do -- a player should not be able to walk
    through furniture a room builder places. These tests exercise the
    `extra_obstacles` parameter threaded through the collision helpers."""

    def test_collides_with_obstacle_detects_extra_obstacle(self):
        assert collides_with_obstacle(120, 120, extra_obstacles=[CUSTOM_OBSTACLE]) is True

    def test_collides_with_obstacle_ignores_extra_obstacle_when_far_away(self):
        assert collides_with_obstacle(700, 50, extra_obstacles=[CUSTOM_OBSTACLE]) is False

    def test_collides_with_obstacle_extra_obstacles_none_does_not_raise(self):
        assert collides_with_obstacle(700, 50, extra_obstacles=None) is False

    def test_resolve_collision_blocks_desired_position_inside_extra_obstacle(self):
        current = {"x": 60.0, "y": 120.0}
        desired = {"x": 120.0, "y": 120.0}
        result = resolve_collision(current, desired, extra_obstacles=[CUSTOM_OBSTACLE])
        assert result != desired
        assert not collides_with_obstacle(result["x"], result["y"], extra_obstacles=[CUSTOM_OBSTACLE])

    def test_move_toward_is_blocked_by_extra_obstacle(self):
        current = {"x": 60.0, "y": 120.0}
        target = {"x": 120.0, "y": 120.0}
        result = move_toward(current, target, 100, extra_obstacles=[CUSTOM_OBSTACLE])
        assert not collides_with_obstacle(result["x"], result["y"], extra_obstacles=[CUSTOM_OBSTACLE])

    def test_move_by_direction_is_blocked_by_extra_obstacle(self):
        current = {"x": 60.0, "y": 120.0}
        result = move_by_direction(current, {"x": 1, "y": 0}, 40, extra_obstacles=[CUSTOM_OBSTACLE])
        assert not collides_with_obstacle(result["x"], result["y"], extra_obstacles=[CUSTOM_OBSTACLE])

    def test_move_by_direction_without_extra_obstacles_is_unaffected(self):
        # Regression: adding the extra_obstacles parameter must not change
        # behavior for callers that don't pass it (default None).
        current = create_position(100, 100)
        result = move_by_direction(current, {"x": 0, "y": -1}, 5)
        assert result["y"] == 95


class TestWallSlideAssist:
    """Regression tests for players getting permanently stuck against
    furniture when holding a single direction key (no lateral input). Without
    a lateral component to slide with, the naive axis-preserving slide
    degenerates to "stay put forever", which made large parts of the lobby
    (and, in practice, the newly added tile edges) unreachable by straight-
    line keyboard movement alone."""

    TABLE = next(o for o in OBSTACLES if o["id"] == "table")

    def test_moving_straight_up_into_an_obstacle_still_makes_progress(self):
        # Directly below the table's left half -- moving straight up would
        # walk right into it with no horizontal input.
        current = {"x": self.TABLE["x"] + 10, "y": self.TABLE["y"] + self.TABLE["h"] + 20}
        for _ in range(50):
            current = move_by_direction(current, {"x": 0, "y": -1}, 4)
        # Must have moved sideways off of the table's column to get around it,
        # rather than being frozen at the original x.
        assert current["x"] != self.TABLE["x"] + 10
        assert not collides_with_obstacle(current["x"], current["y"])

    def test_moving_straight_up_eventually_clears_the_obstacle_row(self):
        current = {"x": self.TABLE["x"] + 10, "y": self.TABLE["y"] + self.TABLE["h"] + 20}
        for _ in range(200):
            current = move_by_direction(current, {"x": 0, "y": -1}, 4)
        # Should have made real vertical progress past the obstacle, not be
        # stuck oscillating at the same row.
        assert current["y"] < self.TABLE["y"] - 8

    def test_moving_straight_sideways_into_an_obstacle_still_makes_progress(self):
        current = {"x": self.TABLE["x"] - 20, "y": self.TABLE["y"] + 10}
        for _ in range(50):
            current = move_by_direction(current, {"x": 1, "y": 0}, 4)
        assert current["y"] != self.TABLE["y"] + 10
        assert not collides_with_obstacle(current["x"], current["y"])

    def test_resolve_collision_returns_current_when_step_is_zero(self):
        current = {"x": self.TABLE["x"] + 10, "y": self.TABLE["y"] + self.TABLE["h"] + 20}
        desired = dict(current)
        assert resolve_collision(current, desired) == current


class TestEmbeddedObstacleEscape:
    """A room builder can place a new object directly on top of a standing
    player (there's no placement check preventing that). Regression tests
    for the resulting "stuck inside the new item" bug: the player must
    always be able to walk back out of an obstacle they're already standing
    inside, while any obstacle they are NOT currently inside must remain
    fully solid, exactly as before."""

    NEW_ITEM = {"id": "builder-item", "x": 200.0, "y": 200.0, "w": 60.0, "h": 60.0}

    def test_player_embedded_in_new_object_can_walk_out(self):
        # Standing dead center of where an object was just placed.
        current = {"x": 230.0, "y": 230.0}
        assert collides_with_obstacle(current["x"], current["y"], extra_obstacles=[self.NEW_ITEM])

        for _ in range(30):
            current = move_by_direction(current, {"x": 1, "y": 0}, 4, extra_obstacles=[self.NEW_ITEM])

        assert not collides_with_obstacle(current["x"], current["y"], extra_obstacles=[self.NEW_ITEM])

    def test_player_embedded_in_new_object_can_walk_out_via_move_toward(self):
        current = {"x": 230.0, "y": 230.0}
        target = {"x": 400.0, "y": 230.0}
        for _ in range(30):
            current = move_toward(current, target, 4, extra_obstacles=[self.NEW_ITEM])
            if current == target:
                break

        assert not collides_with_obstacle(current["x"], current["y"], extra_obstacles=[self.NEW_ITEM])

    def test_escaping_one_embedding_object_does_not_disable_other_obstacles(self):
        # Player is embedded in NEW_ITEM but a second, separate object sits
        # right next to it -- that second object must still fully block
        # movement, proving the escape only applies to the obstacle the
        # player is actually inside.
        blocker = {"id": "other-item", "x": 260.0, "y": 180.0, "w": 60.0, "h": 100.0}
        current = {"x": 230.0, "y": 230.0}
        desired = {"x": 290.0, "y": 230.0}  # straight into `blocker`

        result = resolve_collision(current, desired, extra_obstacles=[self.NEW_ITEM, blocker])

        assert not collides_with_obstacle(result["x"], result["y"], extra_obstacles=[blocker])

    def test_object_not_currently_overlapped_remains_fully_solid(self):
        # Sanity check unrelated to embedding: a player standing outside an
        # object still cannot walk into it (i.e. the escape fix did not
        # weaken ordinary collision blocking outside of build mode).
        current = {"x": self.NEW_ITEM["x"] - 20, "y": self.NEW_ITEM["y"] + 10}
        for _ in range(30):
            current = move_by_direction(current, {"x": 1, "y": 0}, 4, extra_obstacles=[self.NEW_ITEM])
        assert not collides_with_obstacle(current["x"], current["y"], extra_obstacles=[self.NEW_ITEM])
        # Must have been deflected around it, not passed through its center.
        assert current["x"] < self.NEW_ITEM["x"] + self.NEW_ITEM["w"] / 2 or current["y"] != self.NEW_ITEM["y"] + 10


# A point sitting squarely inside the lobby's hardcoded "table" obstacle.
INSIDE_LOBBY_TABLE = {"x": 400.0, "y": 390.0}


class TestLobbyObstaclesAreLobbyOnly:
    """The hardcoded `OBSTACLES` are the *lobby's* branded furniture -- the
    client only ever draws them when `currentRoomId === 'lobby'`
    (`room-renderer.js`: `if (_isLobby) drawFurniture(ctx)`). Applying them
    to every room made custom/empty rooms contain invisible walls exactly
    where the lobby's sofas/table/DJ deck sit, which players could not walk
    through and could not see. Collision must therefore be opt-out per room."""

    def test_lobby_table_still_blocks_by_default(self):
        # Back-compat: existing callers that don't pass the flag are unaffected.
        assert collides_with_obstacle(INSIDE_LOBBY_TABLE["x"], INSIDE_LOBBY_TABLE["y"]) is True

    def test_lobby_table_does_not_block_when_lobby_obstacles_are_excluded(self):
        assert collides_with_obstacle(
            INSIDE_LOBBY_TABLE["x"], INSIDE_LOBBY_TABLE["y"], include_lobby_obstacles=False,
        ) is False

    def test_extra_obstacles_still_block_when_lobby_obstacles_are_excluded(self):
        # Excluding the lobby furniture must not weaken builder-placed collision.
        assert collides_with_obstacle(
            120, 120, extra_obstacles=[CUSTOM_OBSTACLE], include_lobby_obstacles=False,
        ) is True

    def test_resolve_collision_walks_through_lobby_furniture_when_excluded(self):
        # Start clear of the table's collision margin so this exercises
        # ordinary blocking, not the "embedded in an obstacle" escape path.
        current = {"x": 320.0, "y": 390.0}
        desired = dict(INSIDE_LOBBY_TABLE)
        assert resolve_collision(current, desired) != desired  # blocked in the lobby
        assert resolve_collision(current, desired, include_lobby_obstacles=False) == desired

    def test_move_by_direction_walks_through_lobby_furniture_when_excluded(self):
        current = {"x": 320.0, "y": 390.0}
        result = move_by_direction(
            current, {"x": 1, "y": 0}, 80, include_lobby_obstacles=False,
        )
        assert result["x"] == 400.0

    def test_move_toward_walks_through_lobby_furniture_when_excluded(self):
        current = {"x": 320.0, "y": 390.0}
        result = move_toward(
            current, INSIDE_LOBBY_TABLE, 80, include_lobby_obstacles=False,
        )
        assert result == INSIDE_LOBBY_TABLE

    def test_embedded_escape_still_works_when_lobby_obstacles_are_excluded(self):
        # The "walk out of an object placed on top of you" behavior must
        # survive the flag being threaded through resolve_collision.
        item = {"id": "builder-item", "x": 200.0, "y": 200.0, "w": 60.0, "h": 60.0}
        current = {"x": 230.0, "y": 230.0}
        for _ in range(30):
            current = move_by_direction(
                current, {"x": 1, "y": 0}, 4, extra_obstacles=[item], include_lobby_obstacles=False,
            )
        assert not collides_with_obstacle(
            current["x"], current["y"], extra_obstacles=[item], include_lobby_obstacles=False,
        )
