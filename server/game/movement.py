import math
from typing import Any

ROOM_BOUNDS = {
    "width": 800,
    "height": 600,
    "minX": 20,
    "minY": 20,
    "maxX": 780,
    "maxY": 580,
}

# Impassable furniture bounding boxes (x, y, w, h) for the **lobby only**.
#
# These mirror the branded furniture `client/js/room-renderer.js` draws via
# `drawFurniture(ctx)`, which it only ever does while `_isLobby` is true
# (i.e. `currentRoomId === 'lobby'`). Custom/user-built rooms render an
# empty room ready to be furnished through the room builder instead, so
# they must NOT inherit these boxes -- doing so put invisible walls in every
# custom room exactly where the lobby's sofas/table/DJ deck sit. Callers
# opt out with `include_lobby_obstacles=False`; builder-placed furniture is
# passed separately via `extra_obstacles`.
LOBBY_ROOM_ID = "lobby"

OBSTACLES = [
    {"id": "sofa-left",   "x":  48, "y": 330, "w": 166, "h": 80},
    {"id": "sofa-right",  "x": 578, "y": 330, "w": 166, "h": 80},
    {"id": "table",       "x": 348, "y": 370, "w": 104, "h": 42},
    {"id": "dj-deck",     "x": 118, "y": 430, "w":  64, "h": 46},
]

_MARGIN = 8


def _point_overlaps_obstacle(px: float, py: float, obstacle: dict[str, float], margin: float = _MARGIN) -> bool:
    return (obstacle["x"] - margin <= px <= obstacle["x"] + obstacle["w"] + margin and
            obstacle["y"] - margin <= py <= obstacle["y"] + obstacle["h"] + margin)


def collides_with_obstacle(
    px: float, py: float, margin: float = _MARGIN,
    extra_obstacles: list[dict[str, float]] | None = None,
    include_lobby_obstacles: bool = True,
) -> bool:
    """`extra_obstacles` lets callers (e.g. server/main.py) fold in dynamic,
    per-room/per-tile obstacles -- such as builder-placed furniture -- on top
    of the hardcoded lobby `OBSTACLES`, so players can't walk through them.
    Each entry is an `{x, y, w, h}` axis-aligned bounding box.

    `include_lobby_obstacles=False` drops the hardcoded lobby furniture,
    which is only rendered (and therefore should only collide) in the lobby
    itself -- see the `OBSTACLES` comment above."""
    if include_lobby_obstacles:
        for o in OBSTACLES:
            if _point_overlaps_obstacle(px, py, o, margin):
                return True
    if extra_obstacles:
        for o in extra_obstacles:
            if _point_overlaps_obstacle(px, py, o, margin):
                return True
    return False


def _all_obstacles(
    extra_obstacles: list[dict[str, float]] | None, include_lobby_obstacles: bool,
) -> list[dict[str, float]]:
    base = list(OBSTACLES) if include_lobby_obstacles else []
    return base + list(extra_obstacles or [])


def _find_blocking_obstacle(
    px: float, py: float, margin: float = _MARGIN,
    extra_obstacles: list[dict[str, float]] | None = None,
    ignore: list[dict[str, float]] | None = None,
    include_lobby_obstacles: bool = True,
) -> dict[str, float] | None:
    for o in _all_obstacles(extra_obstacles, include_lobby_obstacles):
        if ignore and o in ignore:
            continue
        if _point_overlaps_obstacle(px, py, o, margin):
            return o
    return None


def resolve_collision(
    current: dict[str, float], desired: dict[str, float],
    extra_obstacles: list[dict[str, float]] | None = None,
    include_lobby_obstacles: bool = True,
) -> dict[str, float]:
    # A builder can place a new object directly on top of a standing player
    # (there's no check preventing that), which would otherwise embed the
    # player fully inside a solid obstacle with no legal move left to make --
    # permanently trapping them. Obstacles the player is ALREADY standing
    # inside must not block this move, so they can always walk back out;
    # obstacles they are not currently inside remain fully solid as normal.
    # Once the player steps outside an embedding obstacle's bounds, it goes
    # back to blocking them on the very next call, so this never opens up a
    # way to walk through furniture under ordinary movement.
    embedded_in = [
        o for o in _all_obstacles(extra_obstacles, include_lobby_obstacles)
        if _point_overlaps_obstacle(current["x"], current["y"], o)
    ]

    def blocked(px: float, py: float) -> bool:
        return _find_blocking_obstacle(
            px, py, extra_obstacles=extra_obstacles, ignore=embedded_in,
            include_lobby_obstacles=include_lobby_obstacles,
        ) is not None

    if not blocked(desired["x"], desired["y"]):
        return desired
    slide_x = {"x": desired["x"], "y": current["y"]}
    if slide_x != current and not blocked(slide_x["x"], slide_x["y"]):
        return clamp_position(slide_x)
    slide_y = {"x": current["x"], "y": desired["y"]}
    if slide_y != current and not blocked(slide_y["x"], slide_y["y"]):
        return clamp_position(slide_y)

    # Pure single-axis input (straight up/down/left/right) that runs head-on
    # into an obstacle has no lateral component for the two slide attempts
    # above to work with -- both degenerate back to the current position
    # (skipped by the `!= current` checks above), leaving the player
    # permanently stuck against furniture with no way to route around it
    # other than manually pressing a perpendicular key.
    # Nudge the player sideways (relative to whichever side of the obstacle
    # they're already on) by the same step distance, so holding a single
    # direction key naturally slides around the obstacle's corner instead of
    # dead-stopping against it.
    step = calculate_distance(current, desired)
    if step <= 0:
        return current
    blocking = _find_blocking_obstacle(
        desired["x"], desired["y"], extra_obstacles=extra_obstacles, ignore=embedded_in,
        include_lobby_obstacles=include_lobby_obstacles,
    )
    if blocking is not None:
        moving_vertically = desired["x"] == current["x"] and desired["y"] != current["y"]
        moving_horizontally = desired["y"] == current["y"] and desired["x"] != current["x"]
        if moving_vertically:
            box_center_x = blocking["x"] + blocking["w"] / 2
            nudge_dir = -1 if current["x"] < box_center_x else 1
            nudge = {"x": current["x"] + nudge_dir * step, "y": current["y"]}
            if not blocked(nudge["x"], nudge["y"]):
                return clamp_position(nudge)
        elif moving_horizontally:
            box_center_y = blocking["y"] + blocking["h"] / 2
            nudge_dir = -1 if current["y"] < box_center_y else 1
            nudge = {"x": current["x"], "y": current["y"] + nudge_dir * step}
            if not blocked(nudge["x"], nudge["y"]):
                return clamp_position(nudge)

    return current


def create_position(x: float | None = None, y: float | None = None) -> dict[str, float]:
    return {
        "x": x if x is not None else ROOM_BOUNDS["width"] / 2,
        "y": y if y is not None else ROOM_BOUNDS["height"] / 2,
    }


def calculate_distance(a: dict[str, float], b: dict[str, float]) -> float:
    dx = b["x"] - a["x"]
    dy = b["y"] - a["y"]
    return math.sqrt(dx * dx + dy * dy)


def move_toward(
    current: dict[str, float], target: dict[str, float], step: float,
    extra_obstacles: list[dict[str, float]] | None = None,
    include_lobby_obstacles: bool = True,
) -> dict[str, float]:
    dist = calculate_distance(current, target)
    if dist <= step:
        desired = {"x": target["x"], "y": target["y"]}
    else:
        ratio = step / dist
        desired = {
            "x": current["x"] + (target["x"] - current["x"]) * ratio,
            "y": current["y"] + (target["y"] - current["y"]) * ratio,
        }
    return resolve_collision(
        current, desired, extra_obstacles=extra_obstacles,
        include_lobby_obstacles=include_lobby_obstacles,
    )


def move_by_direction(
    current: dict[str, float], direction: dict[str, float], step: float,
    extra_obstacles: list[dict[str, float]] | None = None,
    include_lobby_obstacles: bool = True,
) -> dict[str, float]:
    dx = direction.get("x", 0)
    dy = direction.get("y", 0)
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0:
        return {"x": current["x"], "y": current["y"]}
    norm_x = dx / length
    norm_y = dy / length
    return resolve_collision(current, {
        "x": current["x"] + norm_x * step,
        "y": current["y"] + norm_y * step,
    }, extra_obstacles=extra_obstacles, include_lobby_obstacles=include_lobby_obstacles)


def clamp_position(pos: dict[str, float]) -> dict[str, float]:
    return {
        "x": max(ROOM_BOUNDS["minX"], min(ROOM_BOUNDS["maxX"], pos["x"])),
        "y": max(ROOM_BOUNDS["minY"], min(ROOM_BOUNDS["maxY"], pos["y"])),
    }


def is_within_bounds(pos: dict[str, float]) -> bool:
    return (
        ROOM_BOUNDS["minX"] <= pos["x"] <= ROOM_BOUNDS["maxX"]
        and ROOM_BOUNDS["minY"] <= pos["y"] <= ROOM_BOUNDS["maxY"]
    )
