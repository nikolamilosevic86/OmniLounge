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

# Impassable furniture bounding boxes (x, y, w, h)
OBSTACLES = [
    {"id": "sofa-left",   "x":  48, "y": 330, "w": 166, "h": 80},
    {"id": "sofa-right",  "x": 578, "y": 330, "w": 166, "h": 80},
    {"id": "table",       "x": 348, "y": 370, "w": 104, "h": 42},
    {"id": "dj-deck",     "x": 118, "y": 430, "w":  64, "h": 46},
]

_MARGIN = 8


def collides_with_obstacle(px: float, py: float, margin: float = _MARGIN) -> bool:
    for o in OBSTACLES:
        if (o["x"] - margin <= px <= o["x"] + o["w"] + margin and
                o["y"] - margin <= py <= o["y"] + o["h"] + margin):
            return True
    return False


def resolve_collision(current: dict[str, float], desired: dict[str, float]) -> dict[str, float]:
    if not collides_with_obstacle(desired["x"], desired["y"]):
        return desired
    slide_x = {"x": desired["x"], "y": current["y"]}
    if not collides_with_obstacle(slide_x["x"], slide_x["y"]):
        return clamp_position(slide_x)
    slide_y = {"x": current["x"], "y": desired["y"]}
    if not collides_with_obstacle(slide_y["x"], slide_y["y"]):
        return clamp_position(slide_y)
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


def move_toward(current: dict[str, float], target: dict[str, float], step: float) -> dict[str, float]:
    dist = calculate_distance(current, target)
    if dist <= step:
        desired = {"x": target["x"], "y": target["y"]}
    else:
        ratio = step / dist
        desired = {
            "x": current["x"] + (target["x"] - current["x"]) * ratio,
            "y": current["y"] + (target["y"] - current["y"]) * ratio,
        }
    return resolve_collision(current, desired)


def move_by_direction(current: dict[str, float], direction: dict[str, float], step: float) -> dict[str, float]:
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
    })


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
