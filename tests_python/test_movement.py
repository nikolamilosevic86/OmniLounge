from server.game.movement import (
    ROOM_BOUNDS,
    calculate_distance,
    clamp_position,
    create_position,
    is_within_bounds,
    move_by_direction,
    move_toward,
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
