import pytest

from server.game.movement import ROOM_BOUNDS
from server.game.npc_guide import (
    MAX_WAYPOINTS,
    STATUS_FINISHED,
    STATUS_PAUSED,
    STATUS_RETURNING,
    STATUS_WALKING,
    WAYPOINT_PAUSE_MS,
    GuideEngine,
    clamp_waypoint,
    step_toward,
)


class TestClampWaypoint:
    def test_keeps_in_bounds_point_unchanged(self):
        assert clamp_waypoint(400, 300) == {"x": 400.0, "y": 300.0}

    def test_clamps_point_outside_room_bounds(self):
        clamped = clamp_waypoint(-500, 99999)
        assert clamped == {"x": float(ROOM_BOUNDS["minX"]), "y": float(ROOM_BOUNDS["maxY"])}

    @pytest.mark.parametrize("bad", ["100", None, True, [1]])
    def test_rejects_non_numeric_coordinates(self, bad):
        with pytest.raises(ValueError):
            clamp_waypoint(bad, 100)
        with pytest.raises(ValueError):
            clamp_waypoint(100, bad)


class TestStepToward:
    def test_moves_by_at_most_speed(self):
        position, arrived = step_toward({"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.0}, speed=10.0)
        assert position == {"x": 10.0, "y": 0.0}
        assert arrived is False

    def test_snaps_onto_target_once_within_one_step(self):
        # Without snapping, a leg whose length is not a multiple of the step
        # size would leave the character oscillating just short of the target.
        position, arrived = step_toward({"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 4.0}, speed=10.0)
        assert position == {"x": 3.0, "y": 4.0}
        assert arrived is True

    def test_already_at_target_reports_arrival(self):
        position, arrived = step_toward({"x": 5.0, "y": 5.0}, {"x": 5.0, "y": 5.0}, speed=2.0)
        assert position == {"x": 5.0, "y": 5.0}
        assert arrived is True

    def test_diagonal_step_length_equals_speed(self):
        position, _ = step_toward({"x": 0.0, "y": 0.0}, {"x": 300.0, "y": 400.0}, speed=5.0)
        assert position["x"] == pytest.approx(3.0)
        assert position["y"] == pytest.approx(4.0)


class TestRouteAuthoring:
    def test_add_and_list_waypoints_preserves_order(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100, "The library")
        guide.add_waypoint("npc-1", "wp-2", 200, 200, "The lab")
        assert [w["waypointId"] for w in guide.list_waypoints("npc-1")] == ["wp-1", "wp-2"]
        assert guide.list_waypoints("npc-1")[0]["label"] == "The library"

    def test_waypoint_coordinates_are_clamped_on_add(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", -40, 5000)
        assert guide.list_waypoints("npc-1")[0]["x"] == float(ROOM_BOUNDS["minX"])
        assert guide.list_waypoints("npc-1")[0]["y"] == float(ROOM_BOUNDS["maxY"])

    def test_blank_label_is_stored_as_none(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100, "   ")
        assert guide.list_waypoints("npc-1")[0]["label"] is None

    def test_rejects_overlong_label(self):
        guide = GuideEngine()
        with pytest.raises(ValueError, match="characters or fewer"):
            guide.add_waypoint("npc-1", "wp-1", 100, 100, "x" * 500)

    def test_rejects_duplicate_waypoint_id(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100)
        with pytest.raises(ValueError, match="already exists"):
            guide.add_waypoint("npc-1", "wp-1", 200, 200)

    def test_enforces_max_waypoints(self):
        guide = GuideEngine()
        for i in range(MAX_WAYPOINTS):
            guide.add_waypoint("npc-1", f"wp-{i}", 100, 100)
        with pytest.raises(ValueError, match="cannot exceed"):
            guide.add_waypoint("npc-1", "wp-overflow", 100, 100)

    def test_routes_are_isolated_per_object(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100)
        assert guide.list_waypoints("npc-2") == []

    def test_remove_waypoint(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100)
        guide.add_waypoint("npc-1", "wp-2", 200, 200)
        remaining = guide.remove_waypoint("npc-1", "wp-1")
        assert [w["waypointId"] for w in remaining] == ["wp-2"]

    def test_remove_unknown_waypoint_raises(self):
        guide = GuideEngine()
        with pytest.raises(KeyError):
            guide.remove_waypoint("npc-1", "nope")

    def test_reorder_waypoints(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100)
        guide.add_waypoint("npc-1", "wp-2", 200, 200)
        reordered = guide.move_waypoint("npc-1", "wp-2", "up")
        assert [w["waypointId"] for w in reordered] == ["wp-2", "wp-1"]

    def test_reorder_at_boundary_is_a_noop(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100)
        guide.add_waypoint("npc-1", "wp-2", 200, 200)
        assert [w["waypointId"] for w in guide.move_waypoint("npc-1", "wp-1", "up")] == ["wp-1", "wp-2"]

    def test_reorder_rejects_invalid_direction(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100)
        with pytest.raises(ValueError, match="direction"):
            guide.move_waypoint("npc-1", "wp-1", "sideways")

    def test_clear_waypoints(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100)
        assert guide.clear_waypoints("npc-1") == []
        assert guide.has_route("npc-1") is False

    def test_has_route_reflects_emptiness(self):
        guide = GuideEngine()
        assert guide.has_route("npc-1") is False
        guide.add_waypoint("npc-1", "wp-1", 100, 100)
        assert guide.has_route("npc-1") is True


class TestTourLifecycle:
    def _guide_with_route(self):
        guide = GuideEngine()
        guide.add_waypoint("npc-1", "wp-1", 100, 100, "First stop")
        guide.add_waypoint("npc-1", "wp-2", 200, 100, "Second stop")
        return guide

    def test_cannot_start_tour_without_a_route(self):
        guide = GuideEngine()
        with pytest.raises(ValueError, match="no tour route"):
            guide.start_tour("npc-1", {"x": 0, "y": 0}, "player-1")

    def test_start_tour_registers_follower(self):
        guide = self._guide_with_route()
        tour = guide.start_tour("npc-1", {"x": 0, "y": 0}, "player-1")
        assert tour["status"] == STATUS_WALKING
        assert tour["followers"] == ["player-1"]
        assert tour["waypointCount"] == 2
        assert guide.is_following("npc-1", "player-1") is True

    def test_second_learner_joins_the_same_tour(self):
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 0}, "player-1")
        tour = guide.start_tour("npc-1", {"x": 0, "y": 0}, "player-2")
        assert tour["followers"] == ["player-1", "player-2"]

    def test_joining_twice_does_not_duplicate_follower(self):
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 0}, "player-1")
        tour = guide.start_tour("npc-1", {"x": 0, "y": 0}, "player-1")
        assert tour["followers"] == ["player-1"]

    def test_tour_walks_toward_the_first_waypoint(self):
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-1")
        result = guide.tick("npc-1", {"x": 0.0, "y": 100.0}, now_ms=0.0)
        assert result["moved"] is True
        assert 0 < result["position"]["x"] < 100
        assert result["status"] == STATUS_WALKING

    def test_tick_without_a_tour_returns_none(self):
        guide = self._guide_with_route()
        assert guide.tick("npc-1", {"x": 0.0, "y": 100.0}, now_ms=0.0) is None

    def test_arriving_at_a_waypoint_pauses_and_reports_the_label(self):
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-1")
        result = guide.tick("npc-1", {"x": 99.0, "y": 100.0}, now_ms=1000.0)
        assert result["arrived"]["label"] == "First stop"
        assert result["status"] == STATUS_PAUSED
        assert result["position"] == {"x": 100.0, "y": 100.0}

    def test_stays_paused_until_the_pause_elapses(self):
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-1")
        guide.tick("npc-1", {"x": 99.0, "y": 100.0}, now_ms=1000.0)
        during = guide.tick("npc-1", {"x": 100.0, "y": 100.0}, now_ms=1000.0 + WAYPOINT_PAUSE_MS / 2)
        assert during["moved"] is False
        assert during["status"] == STATUS_PAUSED
        after = guide.tick("npc-1", {"x": 100.0, "y": 100.0}, now_ms=1000.0 + WAYPOINT_PAUSE_MS + 1)
        assert after["moved"] is True
        assert after["status"] == STATUS_WALKING

    def test_full_route_then_returns_to_origin_and_finishes(self):
        guide = self._guide_with_route()
        origin = {"x": 40.0, "y": 100.0}
        guide.start_tour("npc-1", origin, "player-1")
        position = dict(origin)
        now = 0.0
        statuses = []
        for _ in range(2000):
            now += 33.0
            result = guide.tick("npc-1", position, now_ms=now)
            if result is None:
                break
            position = result["position"]
            statuses.append(result["status"])
            if result["finished"]:
                break
        else:
            pytest.fail("tour never finished")
        assert statuses[-1] == STATUS_FINISHED
        assert position["x"] == pytest.approx(origin["x"])
        assert position["y"] == pytest.approx(origin["y"])
        assert guide.public_tour("npc-1") is None

    def test_visits_every_waypoint_in_order(self):
        guide = self._guide_with_route()
        origin = {"x": 40.0, "y": 100.0}
        guide.start_tour("npc-1", origin, "player-1")
        position = dict(origin)
        now = 0.0
        visited = []
        for _ in range(2000):
            now += 33.0
            result = guide.tick("npc-1", position, now_ms=now)
            if result is None:
                break
            position = result["position"]
            if result["arrived"]:
                visited.append(result["arrived"]["waypointId"])
            if result["finished"]:
                break
        assert visited == ["wp-1", "wp-2"]

    def test_last_follower_leaving_sends_the_character_home(self):
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-1")
        tour = guide.leave_tour("npc-1", "player-1")
        assert tour["status"] == STATUS_RETURNING
        assert tour["followers"] == []

    def test_tour_continues_while_another_follower_remains(self):
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-1")
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-2")
        tour = guide.leave_tour("npc-1", "player-1")
        assert tour["status"] == STATUS_WALKING
        assert tour["followers"] == ["player-2"]

    def test_leaving_a_tour_that_is_not_running_is_a_noop(self):
        guide = self._guide_with_route()
        assert guide.leave_tour("npc-1", "player-1") is None

    def test_editing_the_route_cancels_an_in_progress_tour(self):
        # A tour holds an index into the route; letting an author delete a
        # waypoint mid-tour would leave that index dangling.
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-1")
        guide.remove_waypoint("npc-1", "wp-1")
        assert guide.public_tour("npc-1") is None

    def test_clearing_the_route_cancels_an_in_progress_tour(self):
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-1")
        guide.clear_waypoints("npc-1")
        assert guide.public_tour("npc-1") is None

    def test_discard_drops_route_and_tour(self):
        guide = self._guide_with_route()
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-1")
        guide.discard("npc-1")
        assert guide.list_waypoints("npc-1") == []
        assert guide.public_tour("npc-1") is None
        assert guide.active_object_ids() == []

    def test_active_object_ids_tracks_running_tours(self):
        guide = self._guide_with_route()
        assert guide.active_object_ids() == []
        guide.start_tour("npc-1", {"x": 0, "y": 100}, "player-1")
        assert guide.active_object_ids() == ["npc-1"]
        guide.stop_tour("npc-1")
        assert guide.active_object_ids() == []
