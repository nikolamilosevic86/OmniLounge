from server.game.movement import (
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
