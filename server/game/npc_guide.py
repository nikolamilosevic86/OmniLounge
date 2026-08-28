"""AI character guided-tour ("follow me") routes and runtime movement.

An `ai_character` room object can be given an ordered list of **waypoints**
forming a tour route. A learner who talks to the character can accept a
"follow me" invitation, which starts a tour: the character walks from its
placed position through each waypoint in order (pausing briefly at each so
followers can catch up and read the waypoint's spoken label), then walks
back to where it was placed so the room is left exactly as the author
arranged it and the next learner gets the same tour from the start.

Everything here is deliberately free of socket/room plumbing so the walking
and route-editing rules can be unit tested directly; `RoomBuilderState`
owns permissions and `server/main.py`'s game loop drives `tick_all()`.
"""

import math
from typing import Any

from server.game.movement import ROOM_BOUNDS

MAX_WAYPOINTS = 12
MAX_WAYPOINT_LABEL_LENGTH = 120

# Slightly slower than a player's MOVE_SPEED so a following learner can
# comfortably keep up with (and not overshoot) their guide.
NPC_MOVE_SPEED = 2.4
WAYPOINT_ARRIVAL_RADIUS = 4.0
WAYPOINT_PAUSE_MS = 2200.0

STATUS_WALKING = "walking"
STATUS_PAUSED = "paused"
STATUS_RETURNING = "returning"
STATUS_FINISHED = "finished"


def clamp_waypoint(x: float, y: float) -> dict[str, float]:
    """Clamp an author-supplied waypoint into the walkable room bounds so a
    tour can never send a character (and the learners following it) off
    into unreachable space where it would stall forever."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"x must be numeric, got {x!r}")
    if isinstance(y, bool) or not isinstance(y, (int, float)):
        raise ValueError(f"y must be numeric, got {y!r}")
    return {
        "x": float(min(max(x, ROOM_BOUNDS["minX"]), ROOM_BOUNDS["maxX"])),
        "y": float(min(max(y, ROOM_BOUNDS["minY"]), ROOM_BOUNDS["maxY"])),
    }


def step_toward(
    position: dict[str, float], target: dict[str, float], speed: float = NPC_MOVE_SPEED,
) -> tuple[dict[str, float], bool]:
    """Move `position` toward `target` by at most `speed` pixels.

    Returns `(new_position, arrived)`. `arrived` is True once the remaining
    distance is within `WAYPOINT_ARRIVAL_RADIUS`, in which case the returned
    position snaps exactly onto the target -- without snapping, a route leg
    whose length isn't an exact multiple of `speed` would leave the
    character permanently jittering a fraction of a pixel short of it.
    """
    dx = target["x"] - position["x"]
    dy = target["y"] - position["y"]
    distance = math.hypot(dx, dy)
    if distance <= max(speed, WAYPOINT_ARRIVAL_RADIUS):
        return {"x": float(target["x"]), "y": float(target["y"])}, True
    ratio = speed / distance
    return {"x": position["x"] + dx * ratio, "y": position["y"] + dy * ratio}, False


class GuideEngine:
    """Per-`ai_character`-object tour routes plus at most one in-progress
    tour per character."""

    def __init__(self) -> None:
        self._routes: dict[str, list[dict[str, Any]]] = {}
        self._runs: dict[str, dict[str, Any]] = {}

    # ─── Route authoring ────────────────────────────────────────────────

    def add_waypoint(
        self, object_id: str, waypoint_id: str, x: float, y: float, label: str | None = None,
    ) -> list[dict[str, Any]]:
        route = self._routes.setdefault(object_id, [])
        if len(route) >= MAX_WAYPOINTS:
            raise ValueError(f"a tour route cannot exceed {MAX_WAYPOINTS} waypoints")
        if any(w["waypointId"] == waypoint_id for w in route):
            raise ValueError(f"waypoint id already exists: {waypoint_id}")
        if label is not None:
            label = label.strip() or None
        if label and len(label) > MAX_WAYPOINT_LABEL_LENGTH:
            raise ValueError(f"label must be {MAX_WAYPOINT_LABEL_LENGTH} characters or fewer")
        point = clamp_waypoint(x, y)
        route.append({"waypointId": waypoint_id, "x": point["x"], "y": point["y"], "label": label})
        return self.list_waypoints(object_id)

    def remove_waypoint(self, object_id: str, waypoint_id: str) -> list[dict[str, Any]]:
        route = self._routes.get(object_id, [])
        remaining = [w for w in route if w["waypointId"] != waypoint_id]
        if len(remaining) == len(route):
            raise KeyError(f"unknown waypoint: {waypoint_id}")
        self._routes[object_id] = remaining
        # Editing the route mid-tour would leave the run pointing at a stale
        # index (or one past the end), so cancel any tour in progress.
        self.stop_tour(object_id)
        return self.list_waypoints(object_id)

    def move_waypoint(self, object_id: str, waypoint_id: str, direction: str) -> list[dict[str, Any]]:
        if direction not in ("up", "down"):
            raise ValueError("direction must be 'up' or 'down'")
        route = self._routes.get(object_id, [])
        index = next((i for i, w in enumerate(route) if w["waypointId"] == waypoint_id), None)
        if index is None:
            raise KeyError(f"unknown waypoint: {waypoint_id}")
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(route):
            route[index], route[target] = route[target], route[index]
            self.stop_tour(object_id)
        return self.list_waypoints(object_id)

    def clear_waypoints(self, object_id: str) -> list[dict[str, Any]]:
        self._routes.pop(object_id, None)
        self.stop_tour(object_id)
        return []

    def list_waypoints(self, object_id: str) -> list[dict[str, Any]]:
        return [dict(w) for w in self._routes.get(object_id, [])]

    def has_route(self, object_id: str) -> bool:
        return bool(self._routes.get(object_id))

    def discard(self, object_id: str) -> None:
        """Drop all route/tour state for a deleted character object."""
        self._routes.pop(object_id, None)
        self._runs.pop(object_id, None)

    # ─── Tour runtime ───────────────────────────────────────────────────

    def start_tour(
        self, object_id: str, origin: dict[str, float], follower_id: str, now_ms: float = 0.0,
    ) -> dict[str, Any]:
        """Begin (or join, if already running) a guided tour.

        `origin` is the character's currently placed position, remembered so
        the character can walk back to it when the tour ends.
        """
        route = self._routes.get(object_id)
        if not route:
            raise ValueError("this character has no tour route to follow")
        run = self._runs.get(object_id)
        if run is None:
            run = {
                "origin": {"x": float(origin["x"]), "y": float(origin["y"])},
                "waypointIndex": 0,
                "status": STATUS_WALKING,
                "pauseUntil": 0.0,
                "followers": [],
                "startedAt": now_ms,
            }
            self._runs[object_id] = run
        if follower_id not in run["followers"]:
            run["followers"].append(follower_id)
        return self.public_tour(object_id)

    def leave_tour(self, object_id: str, follower_id: str) -> dict[str, Any] | None:
        """Remove one follower. The tour keeps running while anyone else is
        still following; once the last follower drops out the character
        heads back to where it was placed rather than stopping dead in the
        middle of the room."""
        run = self._runs.get(object_id)
        if run is None:
            return None
        if follower_id in run["followers"]:
            run["followers"].remove(follower_id)
        if not run["followers"] and run["status"] != STATUS_RETURNING:
            run["status"] = STATUS_RETURNING
            run["pauseUntil"] = 0.0
        return self.public_tour(object_id)

    def stop_tour(self, object_id: str) -> None:
        """Cancel a tour outright (route edited, character deleted, ...).
        Callers that want the character returned to its placed position
        should use the `origin` from `get_run` before calling this."""
        self._runs.pop(object_id, None)

    def get_run(self, object_id: str) -> dict[str, Any] | None:
        run = self._runs.get(object_id)
        return dict(run) if run else None

    def public_tour(self, object_id: str) -> dict[str, Any] | None:
        run = self._runs.get(object_id)
        if run is None:
            return None
        return {
            "status": run["status"],
            "waypointIndex": run["waypointIndex"],
            "waypointCount": len(self._routes.get(object_id, [])),
            "followers": list(run["followers"]),
        }

    def is_following(self, object_id: str, follower_id: str) -> bool:
        run = self._runs.get(object_id)
        return bool(run and follower_id in run["followers"])

    def active_object_ids(self) -> list[str]:
        return list(self._runs.keys())

    def tick(
        self, object_id: str, position: dict[str, float], now_ms: float,
    ) -> dict[str, Any] | None:
        """Advance one tour by a single game-loop tick.

        Returns None when the character has no tour in progress, otherwise a
        summary of this tick: the character's new position, the tour status,
        the waypoint it just reached (if any, so the caller can make the
        character speak that waypoint's label), and whether the tour ended.
        """
        run = self._runs.get(object_id)
        if run is None:
            return None
        route = self._routes.get(object_id, [])

        if run["status"] == STATUS_PAUSED:
            if now_ms < run["pauseUntil"]:
                return self._tick_result(object_id, run, position, moved=False, arrived=None)
            run["status"] = STATUS_WALKING if run["waypointIndex"] < len(route) else STATUS_RETURNING

        if run["status"] == STATUS_RETURNING:
            new_position, arrived = step_toward(position, run["origin"])
            if arrived:
                run["status"] = STATUS_FINISHED
                self._runs.pop(object_id, None)
                return {
                    "objectId": object_id, "position": new_position, "status": STATUS_FINISHED,
                    "waypointIndex": len(route), "arrived": None, "followers": list(run["followers"]),
                    "moved": True, "finished": True,
                }
            return self._tick_result(object_id, run, new_position, moved=True, arrived=None)

        index = run["waypointIndex"]
        if index >= len(route):
            run["status"] = STATUS_RETURNING
            return self._tick_result(object_id, run, position, moved=False, arrived=None)

        target = route[index]
        new_position, arrived = step_toward(position, target)
        if not arrived:
            return self._tick_result(object_id, run, new_position, moved=True, arrived=None)

        run["waypointIndex"] = index + 1
        run["status"] = STATUS_PAUSED
        run["pauseUntil"] = now_ms + WAYPOINT_PAUSE_MS
        return self._tick_result(object_id, run, new_position, moved=True, arrived=dict(target))

    @staticmethod
    def _tick_result(
        object_id: str, run: dict[str, Any], position: dict[str, float],
        moved: bool, arrived: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "objectId": object_id,
            "position": position,
            "status": run["status"],
            "waypointIndex": run["waypointIndex"],
            "arrived": arrived,
            "followers": list(run["followers"]),
            "moved": moved,
            "finished": False,
        }
