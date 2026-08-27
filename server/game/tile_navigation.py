from typing import Literal

from server.game.movement import ROOM_BOUNDS, clamp_position

Direction = Literal["left", "right", "top", "bottom"]

TILE_LIMIT = 2
# Must be >= the clamp margin applied by `clamp_position`/`Room.update_player_
# position` (ROOM_BOUNDS["minX"]/["minY"], and width/height minus maxX/maxY --
# currently 20px on every side). A player's position can never go past that
# clamp boundary, so if EDGE_EPSILON were smaller than the margin (it used to
# be 14 against a 20px margin), the edge-transition threshold would sit just
# outside the reachable range and players would get stuck exactly at the
# clamped boundary, unable to ever trigger a tile transition -- including
# into newly builder-added neighbor tiles.
EDGE_EPSILON = 20.0
TRANSITION_INSET = 28.0


def is_within_world_bounds(tile_x: int, tile_y: int) -> bool:
    return -TILE_LIMIT <= tile_x <= TILE_LIMIT and -TILE_LIMIT <= tile_y <= TILE_LIMIT


def tiles_within_radius(center: tuple[int, int], radius: int) -> set[tuple[int, int]]:
    """Return every in-bounds tile coordinate within Chebyshev `radius` of
    `center` (inclusive of the center tile itself). Used to scope lazy
    object-loading requests to the tiles a client actually needs, instead of
    sending every object in the room."""
    if radius < 0:
        raise ValueError("radius must not be negative")
    cx, cy = center
    return {
        (x, y)
        for x in range(cx - radius, cx + radius + 1)
        for y in range(cy - radius, cy + radius + 1)
        if is_within_world_bounds(x, y)
    }


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
