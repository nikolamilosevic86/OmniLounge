import pytest

from server.game.tile_navigation import (
    EDGE_EPSILON,
    TILE_LIMIT,
    can_add_neighbor_tile,
    detect_edge_transition,
    is_within_world_bounds,
    tiles_within_radius,
    transition_to_neighbor,
)


@pytest.mark.parametrize(
    "tile_x,tile_y,expected",
    [
        (0, 0, True),
        (2, 2, True),
        (-2, -2, True),
        (3, 0, False),
        (0, -3, False),
    ],
)
def test_is_within_world_bounds(tile_x, tile_y, expected):
    assert is_within_world_bounds(tile_x, tile_y) is expected


def test_detect_edge_transition_right_edge():
    position = {"x": 800.0 - EDGE_EPSILON / 2, "y": 300.0}
    result = detect_edge_transition(position)
    assert result == "right"


def test_detect_edge_transition_no_edge():
    position = {"x": 400.0, "y": 300.0}
    result = detect_edge_transition(position)
    assert result is None


def test_transition_to_neighbor_right_keeps_vertical_position():
    position = {"x": 799.0, "y": 444.0}
    current_tile = {"x": 0, "y": 0}
    result = transition_to_neighbor(current_tile, position, "right")
    assert result["tile"] == {"x": 1, "y": 0}
    assert result["position"]["x"] < 100.0
    assert result["position"]["y"] == 444.0


def test_transition_to_neighbor_top_keeps_horizontal_position():
    position = {"x": 256.0, "y": 0.0}
    current_tile = {"x": 1, "y": 1}
    result = transition_to_neighbor(current_tile, position, "top")
    assert result["tile"] == {"x": 1, "y": 0}
    assert result["position"]["y"] > 500.0
    assert result["position"]["x"] == 256.0


def test_transition_rejects_outside_world_limit():
    position = {"x": 799.0, "y": 200.0}
    current_tile = {"x": TILE_LIMIT, "y": 0}
    with pytest.raises(ValueError):
        transition_to_neighbor(current_tile, position, "right")


def test_can_add_neighbor_tile_requires_in_bounds_and_absent():
    existing_tiles = {(0, 0), (1, 0)}
    assert can_add_neighbor_tile(existing_tiles, (0, 0), "top") is True
    assert can_add_neighbor_tile(existing_tiles, (0, 0), "right") is False
    assert can_add_neighbor_tile(existing_tiles, (TILE_LIMIT, 0), "right") is False


def test_tiles_within_radius_zero_returns_only_center():
    assert tiles_within_radius((0, 0), 0) == {(0, 0)}


def test_tiles_within_radius_one_returns_center_and_eight_neighbors():
    result = tiles_within_radius((0, 0), 1)
    assert result == {
        (-1, -1), (0, -1), (1, -1),
        (-1, 0), (0, 0), (1, 0),
        (-1, 1), (0, 1), (1, 1),
    }


def test_tiles_within_radius_clips_to_world_bounds():
    result = tiles_within_radius((TILE_LIMIT, TILE_LIMIT), 1)
    assert all(is_within_world_bounds(x, y) for x, y in result)
    assert (TILE_LIMIT, TILE_LIMIT) in result
    assert (TILE_LIMIT + 1, TILE_LIMIT) not in result


def test_tiles_within_radius_rejects_negative_radius():
    with pytest.raises(ValueError):
        tiles_within_radius((0, 0), -1)
