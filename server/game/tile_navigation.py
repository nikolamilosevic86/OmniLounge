from typing import Literal

from server.game.movement import ROOM_BOUNDS, clamp_position

Direction = Literal["left", "right", "top", "bottom"]

TILE_LIMIT = 2
EDGE_EPSILON = 14.0
TRANSITION_INSET = 28.0


def is_within_world_bounds(tile_x: int, tile_y: int) -> bool:
    return -TILE_LIMIT <= tile_x <= TILE_LIMIT and -TILE_LIMIT <= tile_y <= TILE_LIMIT


def detect_edge_transition(position: dict[str, float]) -> Direction | None:
    x = position["x"]
    y = position["y"]
    if x >= ROOM_BOUNDS["width"] - EDGE_EPSILON:
        return "right"
    if x <= EDGE_EPSILON:
        return "left"
    if y <= EDGE_EPSILON:
        return "top"
    if y >= ROOM_BOUNDS["height"] - EDGE_EPSILON:
        return "bottom"
    return None


def _neighbor_tile(tile: tuple[int, int], direction: Direction) -> tuple[int, int]:
    x, y = tile
    if direction == "right":
        return x + 1, y
    if direction == "left":
        return x - 1, y
    if direction == "top":
        return x, y - 1
    return x, y + 1


def transition_to_neighbor(
    current_tile: dict[str, int],
    position: dict[str, float],
    direction: Direction,
) -> dict[str, dict[str, float] | dict[str, int]]:
    next_tile_x, next_tile_y = _neighbor_tile((current_tile["x"], current_tile["y"]), direction)
    if not is_within_world_bounds(next_tile_x, next_tile_y):
        raise ValueError("transition exceeds world bounds")

    if direction == "right":
        next_position = {"x": TRANSITION_INSET, "y": position["y"]}
    elif direction == "left":
        next_position = {"x": ROOM_BOUNDS["width"] - TRANSITION_INSET, "y": position["y"]}
    elif direction == "top":
        next_position = {"x": position["x"], "y": ROOM_BOUNDS["height"] - TRANSITION_INSET}
    else:
        next_position = {"x": position["x"], "y": TRANSITION_INSET}

    return {
        "tile": {"x": next_tile_x, "y": next_tile_y},
        "position": clamp_position(next_position),
    }


def can_add_neighbor_tile(
    existing_tiles: set[tuple[int, int]],
    base_tile: tuple[int, int],
    direction: Direction,
) -> bool:
    next_tile = _neighbor_tile(base_tile, direction)
    return is_within_world_bounds(*next_tile) and next_tile not in existing_tiles
