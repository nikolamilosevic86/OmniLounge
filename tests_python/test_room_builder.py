import pytest
from pydantic import ValidationError

from server.game.room_builder import RoomBuilderState


# ─── Tile graph editor ──────────────────────────────────────────────────────

class TestTileGraph:
    def setup_method(self):
        self.builder = RoomBuilderState()

    def test_starts_with_origin_tile(self):
        tiles = self.builder.list_tiles()
        assert tiles == [{"x": 0, "y": 0, "label": None, "purposeTag": None,
                           "backgroundStyle": None, "ambianceStyle": None, "isSpawn": True}]

    def test_add_tile_creates_neighbor(self):
        created = self.builder.add_tile((0, 0), "right")
        assert created == (1, 0)
        assert self.builder.get_tile((1, 0)) is not None

    def test_add_tile_rejects_duplicate(self):
        self.builder.add_tile((0, 0), "right")
        assert self.builder.add_tile((0, 0), "right") is None

    def test_add_tile_rejects_out_of_world_bounds(self):
        tile = (0, 0)
        for _ in range(2):
            tile = self.builder.add_tile(tile, "right")
        # tile is now (2, 0); one more step would exceed the 5x5 [-2, 2] bound
        assert self.builder.add_tile(tile, "right") is None

    def test_configure_tile_sets_visual_fields(self):
        ok = self.builder.configure_tile(
            (0, 0),
            label="Entrance Hall",
            purpose_tag="intro",
            background_style="marble-floor",
            ambiance_style="soft-daylight",
        )
        assert ok is True
        tile = self.builder.get_tile((0, 0))
        assert tile["label"] == "Entrance Hall"
        assert tile["purposeTag"] == "intro"
        assert tile["backgroundStyle"] == "marble-floor"
        assert tile["ambianceStyle"] == "soft-daylight"

    def test_configure_tile_rejects_unknown_tile(self):
        assert self.builder.configure_tile((1, 1), label="Nope") is False

    def test_clone_tile_copies_visuals_into_new_neighbor(self):
        self.builder.configure_tile((0, 0), label="Library", purpose_tag="lesson")
        cloned = self.builder.clone_tile((0, 0), "right")
        assert cloned == (1, 0)
        clone = self.builder.get_tile((1, 0))
        assert clone["label"] == "Library"
        assert clone["purposeTag"] == "lesson"
        assert clone["isSpawn"] is False

    def test_clone_tile_rejects_when_neighbor_occupied(self):
        self.builder.add_tile((0, 0), "right")
        assert self.builder.clone_tile((0, 0), "right") is None

    def test_delete_tile_removes_empty_tile(self):
        self.builder.add_tile((0, 0), "right")
        assert self.builder.delete_tile((1, 0)) is True
        assert self.builder.get_tile((1, 0)) is None

    def test_delete_tile_rejects_spawn_tile(self):
        assert self.builder.delete_tile((0, 0)) is False

    def test_delete_tile_rejects_tile_with_objects(self):
        self.builder.add_tile((0, 0), "right")
        self.builder.create_object(
            "obj-1", "bookshelf", (1, 0), x=100, y=100, width=40, height=60,
        )
        assert self.builder.delete_tile((1, 0)) is False


# ─── Object placement tools ─────────────────────────────────────────────────

class TestObjectPlacement:
    def setup_method(self):
        self.builder = RoomBuilderState()

    def test_create_object_assigns_incrementing_z_index(self):
        first = self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        second = self.builder.create_object("o2", "chair", (0, 0), x=30, y=30, width=20, height=20)
        assert first["zIndex"] == 0
        assert second["zIndex"] == 1

    def test_create_object_rejects_invalid_geometry(self):
        with pytest.raises(ValidationError):
            self.builder.create_object("bad", "table", (0, 0), x=10, y=10, width=0, height=20)

    def test_create_object_rejects_unknown_tile(self):
        with pytest.raises(ValueError):
            self.builder.create_object("o1", "table", (4, 4), x=10, y=10, width=20, height=20)

    def test_create_object_rejects_when_tile_object_budget_exceeded(self):
        from server.game.room_builder import MAX_OBJECTS_PER_TILE

        for i in range(MAX_OBJECTS_PER_TILE):
            self.builder.create_object(f"o{i}", "table", (0, 0), x=10, y=10, width=20, height=20)
        with pytest.raises(ValueError, match="tile object budget"):
            self.builder.create_object("over-budget", "table", (0, 0), x=10, y=10, width=20, height=20)

    def test_create_object_budget_is_tracked_per_tile(self):
        from server.game.room_builder import MAX_OBJECTS_PER_TILE

        self.builder.add_tile((0, 0), "right")
        for i in range(MAX_OBJECTS_PER_TILE):
            self.builder.create_object(f"o{i}", "table", (0, 0), x=10, y=10, width=20, height=20)
        # A different tile should still have its own fresh budget.
        obj = self.builder.create_object("o-other-tile", "table", (1, 0), x=10, y=10, width=20, height=20)
        assert obj["tile"] == (1, 0)

    def test_duplicate_object_rejects_when_tile_object_budget_exceeded(self):
        from server.game.room_builder import MAX_OBJECTS_PER_TILE

        self.builder.create_object("o0", "table", (0, 0), x=10, y=10, width=20, height=20)
        for i in range(1, MAX_OBJECTS_PER_TILE):
            self.builder.create_object(f"o{i}", "table", (0, 0), x=10, y=10, width=20, height=20)
        with pytest.raises(ValueError, match="tile object budget"):
            self.builder.duplicate_object("o0", "o0-clone")

    def test_move_object_updates_position(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        moved = self.builder.move_object("o1", 55, 65)
        assert moved["x"] == 55
        assert moved["y"] == 65

    def test_move_locked_object_is_rejected(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        self.builder.set_locked("o1", True)
        with pytest.raises(PermissionError):
            self.builder.move_object("o1", 55, 65)

    def test_resize_object_updates_dimensions(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        resized = self.builder.resize_object("o1", 40, 50)
        assert resized["width"] == 40
        assert resized["height"] == 50

    def test_resize_object_rejects_non_positive_dimensions(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        with pytest.raises(ValueError):
            self.builder.resize_object("o1", 0, 50)

    def test_rotate_object_normalizes_angle(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        rotated = self.builder.rotate_object("o1", 400)
        assert rotated["rotation"] == 40

    def test_duplicate_object_creates_unlocked_offset_copy(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        self.builder.set_locked("o1", True)
        dup = self.builder.duplicate_object("o1", "o1-copy")
        assert dup["objectId"] == "o1-copy"
        assert dup["x"] == 26
        assert dup["y"] == 26
        assert dup["isLocked"] is False
        assert dup["zIndex"] == 1

    def test_set_locked_prevents_delete(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        self.builder.set_locked("o1", True)
        with pytest.raises(PermissionError):
            self.builder.delete_object("o1")
        self.builder.set_locked("o1", False)
        assert self.builder.delete_object("o1") is True

    def test_bring_to_front_and_send_to_back(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        self.builder.create_object("o2", "chair", (0, 0), x=30, y=30, width=20, height=20)
        self.builder.create_object("o3", "sofa", (0, 0), x=50, y=50, width=20, height=20)
        self.builder.send_to_back("o3")
        assert self.builder.get_object("o3")["zIndex"] < self.builder.get_object("o1")["zIndex"]
        self.builder.bring_to_front("o2")
        z_values = [self.builder.get_object(o)["zIndex"] for o in ("o1", "o2", "o3")]
        assert self.builder.get_object("o2")["zIndex"] == max(z_values)

    def test_list_objects_filters_by_tile(self):
        self.builder.add_tile((0, 0), "right")
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        self.builder.create_object("o2", "chair", (1, 0), x=10, y=10, width=20, height=20)
        assert [o["objectId"] for o in self.builder.list_objects(tile=(0, 0))] == ["o1"]
        assert len(self.builder.list_objects()) == 2

    def test_list_objects_for_tiles_filters_by_a_set_of_tiles(self):
        self.builder.add_tile((0, 0), "right")
        self.builder.add_tile((1, 0), "right")
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        self.builder.create_object("o2", "chair", (1, 0), x=10, y=10, width=20, height=20)
        self.builder.create_object("o3", "sofa", (2, 0), x=10, y=10, width=20, height=20)
        result = self.builder.list_objects_for_tiles({(0, 0), (1, 0)})
        assert {o["objectId"] for o in result} == {"o1", "o2"}

    def test_list_objects_for_tiles_empty_set_returns_no_objects(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20)
        assert self.builder.list_objects_for_tiles(set()) == []

    def test_create_object_rejects_unknown_object_type(self):
        with pytest.raises(ValidationError):
            self.builder.create_object("o1", "spaceship", (0, 0), x=10, y=10, width=20, height=20)


# ─── Phase E: object catalog, style, and interaction ────────────────────────

class TestObjectStyleAndSizePresets:
    def setup_method(self):
        self.builder = RoomBuilderState()

    def test_create_object_without_geometry_uses_type_default_preset(self):
        obj = self.builder.create_object("o1", "chair", (0, 0), x=10, y=10)
        assert obj["sizePreset"] == "S"
        assert (obj["width"], obj["height"]) == (32.0, 32.0)

    def test_create_object_with_explicit_size_preset(self):
        obj = self.builder.create_object("o1", "table", (0, 0), x=10, y=10, size_preset="L")
        assert obj["sizePreset"] == "L"
        assert (obj["width"], obj["height"]) == (72.0, 72.0)

    def test_create_object_with_custom_size_ignores_preset_default(self):
        obj = self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=99, height=44)
        assert obj["sizePreset"] is None
        assert (obj["width"], obj["height"]) == (99, 44)

    def test_create_object_rejects_unknown_size_preset(self):
        with pytest.raises(ValueError):
            self.builder.create_object("o1", "table", (0, 0), x=10, y=10, size_preset="XL")

    def test_create_object_with_color_and_material(self):
        obj = self.builder.create_object(
            "o1", "sofa", (0, 0), x=10, y=10, width=40, height=40, color="navy", material="fabric",
        )
        assert obj["color"] == "navy"
        assert obj["material"] == "fabric"

    def test_create_object_rejects_invalid_color(self):
        with pytest.raises(ValidationError):
            self.builder.create_object("o1", "sofa", (0, 0), x=10, y=10, width=40, height=40, color="rainbow")

    def test_create_object_rejects_invalid_material(self):
        with pytest.raises(ValidationError):
            self.builder.create_object("o1", "sofa", (0, 0), x=10, y=10, width=40, height=40, material="cardboard")

    def test_set_object_style_updates_color_and_material(self):
        self.builder.create_object("o1", "sofa", (0, 0), x=10, y=10, width=40, height=40)
        updated = self.builder.set_object_style("o1", color="gold-accent", material="metal")
        assert updated["color"] == "gold-accent"
        assert updated["material"] == "metal"

    def test_set_object_size_preset_updates_dimensions(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=10, height=10)
        updated = self.builder.set_object_size_preset("o1", "L")
        assert updated["sizePreset"] == "L"
        assert (updated["width"], updated["height"]) == (72.0, 72.0)

    def test_resize_object_clears_size_preset(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, size_preset="M")
        resized = self.builder.resize_object("o1", 12, 12)
        assert resized["sizePreset"] is None


class TestObjectEditPermissions:
    def setup_method(self):
        self.builder = RoomBuilderState()

    def test_creator_can_edit_own_object(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20, created_by="alice")
        moved = self.builder.move_object("o1", 50, 50, requester_id="alice")
        assert (moved["x"], moved["y"]) == (50, 50)

    def test_other_user_cannot_edit_owner_only_object(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20, created_by="alice")
        with pytest.raises(PermissionError):
            self.builder.move_object("o1", 50, 50, requester_id="bob")

    def test_room_host_can_edit_any_object(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20, created_by="alice")
        moved = self.builder.move_object("o1", 50, 50, requester_id="host-1", is_room_host=True)
        assert (moved["x"], moved["y"]) == (50, 50)

    def test_anyone_edit_permission_allows_other_users(self):
        self.builder.create_object(
            "o1", "table", (0, 0), x=10, y=10, width=20, height=20,
            created_by="alice", edit_permission="anyone",
        )
        moved = self.builder.move_object("o1", 50, 50, requester_id="bob")
        assert (moved["x"], moved["y"]) == (50, 50)

    def test_set_object_edit_permission_requires_existing_permission(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20, created_by="alice")
        with pytest.raises(PermissionError):
            self.builder.set_object_edit_permission("o1", "anyone", requester_id="bob")
        updated = self.builder.set_object_edit_permission("o1", "anyone", requester_id="alice")
        assert updated["editPermission"] == "anyone"

    def test_permission_checks_apply_to_resize_rotate_lock_delete(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20, created_by="alice")
        with pytest.raises(PermissionError):
            self.builder.resize_object("o1", 30, 30, requester_id="bob")
        with pytest.raises(PermissionError):
            self.builder.rotate_object("o1", 90, requester_id="bob")
        with pytest.raises(PermissionError):
            self.builder.set_locked("o1", True, requester_id="bob")
        with pytest.raises(PermissionError):
            self.builder.set_object_style("o1", color="white", requester_id="bob")
        with pytest.raises(PermissionError):
            self.builder.delete_object("o1", requester_id="bob")

    def test_requester_none_bypasses_permission_check(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=20, height=20, created_by="alice")
        moved = self.builder.move_object("o1", 5, 5)
        assert (moved["x"], moved["y"]) == (5, 5)


class TestObjectInteractionMenu:
    def setup_method(self):
        self.builder = RoomBuilderState()

    def test_get_interaction_menu_matches_catalog_for_type(self):
        self.builder.create_object("o1", "bookshelf", (0, 0), x=10, y=10, width=40, height=60)
        menu = self.builder.get_object_interaction_menu("o1")
        assert {m["interactionType"] for m in menu} == {"browse_books", "resume_reading"}

    def test_disabled_interactable_object_returns_empty_menu(self):
        self.builder.create_object("o1", "bookshelf", (0, 0), x=10, y=10, width=40, height=60)
        self.builder.set_object_interactable("o1", False)
        assert self.builder.get_object_interaction_menu("o1") == []

    def test_get_object_and_list_objects_include_interactions_field(self):
        self.builder.create_object("o1", "chair", (0, 0), x=10, y=10, width=20, height=20)
        assert {m["interactionType"] for m in self.builder.get_object("o1")["interactions"]} == {"sit"}
        assert {m["interactionType"] for m in self.builder.list_objects()[0]["interactions"]} == {"sit"}

    def test_list_objects_interactions_empty_when_not_interactable(self):
        self.builder.create_object("o1", "chair", (0, 0), x=10, y=10, width=20, height=20)
        self.builder.set_object_interactable("o1", False)
        assert self.builder.list_objects()[0]["interactions"] == []

    def test_interact_with_object_returns_payload(self):
        self.builder.create_object(
            "o1", "chair", (0, 0), x=10, y=10, width=40, height=30,
            config={"seatColor": "red"},
        )
        result = self.builder.interact_with_object("o1", "sit", requester_id="p1", now_ms=1000)
        assert result["interactionType"] == "sit"
        assert result["payload"] == {"seatColor": "red"}

    def test_interact_with_object_rejects_unsupported_interaction(self):
        self.builder.create_object("o1", "table", (0, 0), x=10, y=10, width=40, height=30)
        with pytest.raises(ValueError):
            self.builder.interact_with_object("o1", "watch_video", requester_id="p1", now_ms=1000)

    def test_interact_with_disabled_object_raises(self):
        self.builder.create_object("o1", "tv", (0, 0), x=10, y=10, width=40, height=30)
        self.builder.set_object_interactable("o1", False)
        with pytest.raises(PermissionError):
            self.builder.interact_with_object("o1", "watch_video", requester_id="p1", now_ms=1000)

    def test_interact_with_object_respects_cooldown(self):
        self.builder.create_object(
            "o1", "music_player", (0, 0), x=10, y=10, width=20, height=20,
            interaction_cooldown_ms=5000,
        )
        self.builder.interact_with_object("o1", "play_track", requester_id="p1", now_ms=1000)
        with pytest.raises(PermissionError):
            self.builder.interact_with_object("o1", "play_track", requester_id="p1", now_ms=2000)
        # cooldown elapsed
        result = self.builder.interact_with_object("o1", "play_track", requester_id="p1", now_ms=7000)
        assert result["interactionType"] == "play_track"

    def test_interact_cooldown_is_per_requester(self):
        self.builder.create_object(
            "o1", "music_player", (0, 0), x=10, y=10, width=20, height=20,
            interaction_cooldown_ms=5000,
        )
        self.builder.interact_with_object("o1", "play_track", requester_id="p1", now_ms=1000)
        # a different requester is not affected by p1's cooldown
        result = self.builder.interact_with_object("o1", "play_track", requester_id="p2", now_ms=1100)
        assert result["interactionType"] == "play_track"


# ─── Collision / interaction zone editor ────────────────────────────────────

class TestZones:
    def setup_method(self):
        self.builder = RoomBuilderState()

    def test_create_zone_and_point_containment(self):
        zone = self.builder.create_zone(
            "z1", (0, 0), "interaction", min_x=100, min_y=100, max_x=200, max_y=200,
        )
        assert zone["zoneType"] == "interaction"
        assert self.builder.point_in_zone("z1", 150, 150) is True
        assert self.builder.point_in_zone("z1", 5, 5) is False

    def test_create_zone_rejects_inverted_bounds(self):
        with pytest.raises(ValidationError):
            self.builder.create_zone("z1", (0, 0), "collision", min_x=200, min_y=100, max_x=100, max_y=200)

    def test_create_zone_rejects_invalid_type(self):
        with pytest.raises(ValueError):
            self.builder.create_zone("z1", (0, 0), "not-a-type", min_x=0, min_y=0, max_x=10, max_y=10)

    def test_delete_zone(self):
        self.builder.create_zone("z1", (0, 0), "collision", min_x=0, min_y=0, max_x=10, max_y=10)
        assert self.builder.delete_zone("z1") is True
        assert self.builder.delete_zone("z1") is False

    def test_zones_containing_point_filters_by_tile_and_type(self):
        self.builder.add_tile((0, 0), "right")
        self.builder.create_zone("z1", (0, 0), "interaction", min_x=0, min_y=0, max_x=50, max_y=50)
        self.builder.create_zone("z2", (0, 0), "collision", min_x=0, min_y=0, max_x=50, max_y=50)
        self.builder.create_zone("z3", (1, 0), "interaction", min_x=0, min_y=0, max_x=50, max_y=50)
        hits = self.builder.zones_containing_point((0, 0), 10, 10, zone_type="interaction")
        assert [z["zoneId"] for z in hits] == ["z1"]


# ─── Scripted trigger editor (area-enter events) ────────────────────────────

class TestScriptedTriggers:
    def setup_method(self):
        self.builder = RoomBuilderState()
        self.builder.create_zone("z1", (0, 0), "interaction", min_x=0, min_y=0, max_x=50, max_y=50)

    def test_create_trigger_tied_to_zone(self):
        trigger = self.builder.create_trigger(
            "t1", (0, 0), zone_id="z1", event_type="dialogue",
            payload={"nodeId": "intro-1"},
        )
        assert trigger["eventType"] == "dialogue"
        assert trigger["payload"] == {"nodeId": "intro-1"}

    def test_create_trigger_rejects_unknown_zone(self):
        with pytest.raises(ValueError):
            self.builder.create_trigger("t1", (0, 0), zone_id="missing", event_type="dialogue", payload={})

    def test_one_shot_trigger_fires_once_per_player(self):
        self.builder.create_trigger(
            "t1", (0, 0), zone_id="z1", event_type="dialogue", payload={}, repeatable=False,
        )
        fired_1 = self.builder.evaluate_area_enter("p1", (0, 0), 10, 10, now_ms=1000)
        fired_2 = self.builder.evaluate_area_enter("p1", (0, 0), 12, 12, now_ms=1100)
        # leave the zone then re-enter — should NOT fire again (one-shot)
        self.builder.evaluate_area_enter("p1", (0, 0), 999, 999, now_ms=1200)
        fired_3 = self.builder.evaluate_area_enter("p1", (0, 0), 11, 11, now_ms=1300)
        assert len(fired_1) == 1
        assert fired_1[0]["triggerId"] == "t1"
        assert fired_2 == []  # still inside zone, no re-fire while remaining inside
        assert fired_3 == []  # one-shot already consumed

    def test_repeatable_trigger_respects_cooldown(self):
        self.builder.create_trigger(
            "t1", (0, 0), zone_id="z1", event_type="dialogue", payload={},
            repeatable=True, cooldown_ms=5000,
        )
        fired_1 = self.builder.evaluate_area_enter("p1", (0, 0), 10, 10, now_ms=1000)
        self.builder.evaluate_area_enter("p1", (0, 0), 999, 999, now_ms=1100)  # leave
        fired_2 = self.builder.evaluate_area_enter("p1", (0, 0), 10, 10, now_ms=2000)  # re-enter, cooldown active
        self.builder.evaluate_area_enter("p1", (0, 0), 999, 999, now_ms=2100)  # leave
        fired_3 = self.builder.evaluate_area_enter("p1", (0, 0), 10, 10, now_ms=7000)  # cooldown elapsed
        assert len(fired_1) == 1
        assert fired_2 == []
        assert len(fired_3) == 1

    def test_delete_trigger(self):
        self.builder.create_trigger("t1", (0, 0), zone_id="z1", event_type="dialogue", payload={})
        assert self.builder.delete_trigger("t1") is True
        assert self.builder.evaluate_area_enter("p1", (0, 0), 10, 10, now_ms=1000) == []


# ─── Save draft / publish / rollback ────────────────────────────────────────

class TestVersioning:
    def setup_method(self):
        self.builder = RoomBuilderState()

    def test_save_draft_assigns_incrementing_version_numbers(self):
        v1 = self.builder.save_draft({"tiles": []}, created_by="host-1")
        v2 = self.builder.save_draft({"tiles": ["x"]}, created_by="host-1")
        assert v1["versionNumber"] == 1
        assert v2["versionNumber"] == 2

    def test_publish_marks_version_active(self):
        v1 = self.builder.save_draft({"tiles": []}, created_by="host-1")
        published = self.builder.publish(v1["versionNumber"], published_by="host-1")
        assert published["isActive"] is True
        active = self.builder.get_active_published_version()
        assert active["versionNumber"] == v1["versionNumber"]

    def test_publish_unknown_version_raises(self):
        with pytest.raises(ValueError):
            self.builder.publish(99, published_by="host-1")

    def test_publishing_new_version_deactivates_previous(self):
        v1 = self.builder.save_draft({"tiles": []}, created_by="host-1")
        v2 = self.builder.save_draft({"tiles": ["x"]}, created_by="host-1")
        self.builder.publish(v1["versionNumber"], published_by="host-1")
        self.builder.publish(v2["versionNumber"], published_by="host-1")
        active = self.builder.get_active_published_version()
        assert active["versionNumber"] == v2["versionNumber"]

    def test_rollback_returns_snapshot_content(self):
        v1 = self.builder.save_draft({"tiles": ["a"]}, created_by="host-1")
        self.builder.save_draft({"tiles": ["a", "b"]}, created_by="host-1")
        snapshot = self.builder.rollback(v1["versionNumber"])
        assert snapshot == {"tiles": ["a"]}

    def test_rollback_unknown_version_raises(self):
        with pytest.raises(ValueError):
            self.builder.rollback(42)

    def test_list_versions_ordered_newest_first(self):
        self.builder.save_draft({"tiles": []}, created_by="host-1")
        self.builder.save_draft({"tiles": ["x"]}, created_by="host-1")
        versions = self.builder.list_versions()
        assert [v["versionNumber"] for v in versions] == [2, 1]


class TestBookshelfIntegration:
    def setup_method(self):
        self.builder = RoomBuilderState()
        self.builder.create_object(
            "shelf-1", "bookshelf", (0, 0), x=10, y=10, width=40, height=60, created_by="alice",
        )

    def test_add_book_requires_object_to_be_a_bookshelf(self):
        self.builder.create_object("table-1", "table", (0, 0), x=50, y=50, width=20, height=20)
        with pytest.raises(ValueError):
            self.builder.add_book("table-1", "book-1", title="T", content_body="body")

    def test_add_book_then_list_books_roundtrips(self):
        self.builder.add_book("shelf-1", "book-1", title="Intro", content_body="body")
        books = self.builder.list_books("shelf-1")
        assert [b["bookId"] for b in books] == ["book-1"]

    def test_add_book_requires_edit_permission(self):
        with pytest.raises(PermissionError):
            self.builder.add_book("shelf-1", "book-1", title="T", content_body="b", requester_id="bob")

    def test_add_book_allowed_for_creator(self):
        book = self.builder.add_book("shelf-1", "book-1", title="T", content_body="b", requester_id="alice")
        assert book["bookId"] == "book-1"

    def test_add_book_allowed_for_room_host(self):
        book = self.builder.add_book(
            "shelf-1", "book-1", title="T", content_body="b", requester_id="host-1", is_room_host=True,
        )
        assert book["bookId"] == "book-1"

    def test_remove_book_requires_edit_permission(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b")
        with pytest.raises(PermissionError):
            self.builder.remove_book("shelf-1", "book-1", requester_id="bob")

    def test_remove_book_succeeds_for_creator(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b")
        assert self.builder.remove_book("shelf-1", "book-1", requester_id="alice") is True

    def test_save_reading_progress_then_get_progress_roundtrips(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b")
        self.builder.save_reading_progress("shelf-1", "book-1", "user-1", 0.6, now_ms=1000)
        progress = self.builder.get_reading_progress("shelf-1", "book-1", "user-1")
        assert progress["progress"] == 0.6

    def test_save_reading_progress_does_not_require_edit_permission(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b", requester_id="alice")
        # any room participant can track their own progress, not just the shelf's editors
        progress = self.builder.save_reading_progress("shelf-1", "book-1", "bob", 0.3, now_ms=1000)
        assert progress["progress"] == 0.3

    def test_interact_browse_books_returns_book_list_payload(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b")
        result = self.builder.interact_with_object("shelf-1", "browse_books", requester_id="p1", now_ms=1000)
        assert [b["bookId"] for b in result["payload"]["books"]] == ["book-1"]

    def test_interact_browse_books_includes_requesters_own_progress_per_book(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b")
        self.builder.save_reading_progress("shelf-1", "book-1", "p1", 0.7, now_ms=1000)
        result = self.builder.interact_with_object("shelf-1", "browse_books", requester_id="p1", now_ms=2000)
        assert result["payload"]["books"][0]["progress"] == 0.7

    def test_interact_browse_books_progress_defaults_to_zero_when_unread(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b")
        result = self.builder.interact_with_object("shelf-1", "browse_books", requester_id="p1", now_ms=1000)
        assert result["payload"]["books"][0]["progress"] == 0

    def test_interact_browse_books_progress_is_scoped_per_requester(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b")
        self.builder.save_reading_progress("shelf-1", "book-1", "p1", 0.7, now_ms=1000)
        result = self.builder.interact_with_object("shelf-1", "browse_books", requester_id="p2", now_ms=2000)
        assert result["payload"]["books"][0]["progress"] == 0

    def test_interact_resume_reading_returns_resume_payload(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b")
        self.builder.save_reading_progress("shelf-1", "book-1", "p1", 0.4, now_ms=1000)
        result = self.builder.interact_with_object("shelf-1", "resume_reading", requester_id="p1", now_ms=2000)
        assert result["payload"]["book"]["bookId"] == "book-1"
        assert result["payload"]["progress"] == 0.4

    def test_interact_resume_reading_returns_none_book_when_nothing_in_progress(self):
        self.builder.add_book("shelf-1", "book-1", title="T", content_body="b")
        result = self.builder.interact_with_object("shelf-1", "resume_reading", requester_id="p1", now_ms=1000)
        assert result["payload"]["book"] is None


class TestTvMediaIntegration:
    def setup_method(self):
        self.builder = RoomBuilderState()
        self.builder.create_object(
            "tv-1", "tv", (0, 0), x=10, y=10, width=40, height=30, created_by="alice",
        )

    def test_add_video_requires_object_to_be_a_tv(self):
        self.builder.create_object("table-1", "table", (0, 0), x=50, y=50, width=20, height=20)
        with pytest.raises(ValueError):
            self.builder.add_video("table-1", "video-1", title="T", youtube_video_id="dQw4w9WgXcQ")

    def test_add_video_requires_edit_permission(self):
        with pytest.raises(PermissionError):
            self.builder.add_video("tv-1", "video-1", title="T", youtube_video_id="dQw4w9WgXcQ", requester_id="bob")

    def test_add_video_then_list_videos_roundtrips(self):
        self.builder.add_video("tv-1", "video-1", title="T", youtube_video_id="dQw4w9WgXcQ", requester_id="alice")
        assert [v["videoId"] for v in self.builder.list_videos("tv-1")] == ["video-1"]

    def test_remove_video_requires_edit_permission(self):
        self.builder.add_video("tv-1", "video-1", title="T", youtube_video_id="dQw4w9WgXcQ")
        with pytest.raises(PermissionError):
            self.builder.remove_video("tv-1", "video-1", requester_id="bob")

    def test_interact_open_playlist_returns_video_list(self):
        self.builder.add_video("tv-1", "video-1", title="T", youtube_video_id="dQw4w9WgXcQ")
        result = self.builder.interact_with_object("tv-1", "open_playlist", requester_id="p1", now_ms=1000)
        assert [v["videoId"] for v in result["payload"]["videos"]] == ["video-1"]

    def test_interact_watch_video_returns_default_video_and_no_sync_session(self):
        self.builder.add_video("tv-1", "video-1", title="T", youtube_video_id="dQw4w9WgXcQ")
        result = self.builder.interact_with_object("tv-1", "watch_video", requester_id="p1", now_ms=1000)
        assert result["payload"]["video"]["videoId"] == "video-1"
        assert result["payload"]["syncSession"] is None

    def test_interact_watch_video_returns_none_when_no_videos(self):
        result = self.builder.interact_with_object("tv-1", "watch_video", requester_id="p1", now_ms=1000)
        assert result["payload"]["video"] is None


class TestMusicPlayerMediaIntegration:
    def setup_method(self):
        self.builder = RoomBuilderState()
        self.builder.create_object(
            "player-1", "music_player", (0, 0), x=10, y=10, width=20, height=20, created_by="alice",
        )

    def test_add_track_requires_object_to_be_a_music_player(self):
        self.builder.create_object("table-1", "table", (0, 0), x=50, y=50, width=20, height=20)
        with pytest.raises(ValueError):
            self.builder.add_track("table-1", "track-1", title="T", youtube_video_id="dQw4w9WgXcQ")

    def test_add_track_then_list_tracks_roundtrips(self):
        self.builder.add_track("player-1", "track-1", title="T", youtube_video_id="dQw4w9WgXcQ", requester_id="alice")
        assert [t["trackId"] for t in self.builder.list_tracks("player-1")] == ["track-1"]

    def test_interact_view_playlist_returns_track_list(self):
        self.builder.add_track("player-1", "track-1", title="T", youtube_video_id="dQw4w9WgXcQ")
        result = self.builder.interact_with_object("player-1", "view_playlist", requester_id="p1", now_ms=1000)
        assert [t["trackId"] for t in result["payload"]["tracks"]] == ["track-1"]

    def test_interact_play_track_returns_default_track(self):
        self.builder.add_track("player-1", "track-1", title="T", youtube_video_id="dQw4w9WgXcQ")
        result = self.builder.interact_with_object("player-1", "play_track", requester_id="p1", now_ms=1000)
        assert result["payload"]["track"]["trackId"] == "track-1"

    def test_interact_play_track_defaults_to_the_track_being_listened_to_together(self):
        self.builder.add_track("player-1", "track-1", title="First", youtube_video_id="dQw4w9WgXcQ")
        self.builder.add_track("player-1", "track-2", title="Second", youtube_video_id="oHg5SJYRHA0")
        self.builder.start_watch_sync("player-1", host_id="p1", item_id="track-2", now_ms=1000)
        result = self.builder.interact_with_object("player-1", "play_track", requester_id="p2", now_ms=1000)
        assert result["payload"]["track"]["trackId"] == "track-2"


class TestWatchListenTogetherSync:
    def setup_method(self):
        self.builder = RoomBuilderState()
        self.builder.create_object(
            "tv-1", "tv", (0, 0), x=10, y=10, width=40, height=30, created_by="alice",
        )
        self.builder.add_video("tv-1", "video-1", title="T", youtube_video_id="dQw4w9WgXcQ")

    def test_start_watch_sync_does_not_require_edit_permission(self):
        # any participant can start an opt-in watch party, not just editors
        session = self.builder.start_watch_sync("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        assert session["hostId"] == "p1"

    def test_start_watch_sync_rejects_unknown_item(self):
        with pytest.raises(KeyError):
            self.builder.start_watch_sync("tv-1", host_id="p1", item_id="unknown-video", now_ms=1000)

    def test_start_watch_sync_requires_tv_or_music_player(self):
        self.builder.create_object("table-1", "table", (0, 0), x=50, y=50, width=20, height=20)
        with pytest.raises(ValueError):
            self.builder.start_watch_sync("table-1", host_id="p1", item_id="video-1", now_ms=1000)

    def test_join_and_get_watch_sync(self):
        self.builder.start_watch_sync("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        self.builder.join_watch_sync("tv-1", user_id="p2")
        session = self.builder.get_watch_sync("tv-1", now_ms=1000)
        assert set(session["participants"]) == {"p1", "p2"}

    def test_interact_watch_video_reflects_active_sync_session(self):
        self.builder.start_watch_sync("tv-1", host_id="p1", item_id="video-1", now_ms=1000)
        result = self.builder.interact_with_object("tv-1", "watch_video", requester_id="p2", now_ms=1000)
        assert result["payload"]["syncSession"]["hostId"] == "p1"

    def test_interact_watch_video_defaults_to_the_video_being_watched_together(self):
        # regression: opening the TV while a watch party is active for a
        # *non-first* video must show that video, not an arbitrary default,
        # otherwise the "watching together" status refers to a different
        # video than the one on screen.
        self.builder.add_video("tv-1", "video-2", title="Second", youtube_video_id="oHg5SJYRHA0")
        self.builder.start_watch_sync("tv-1", host_id="p1", item_id="video-2", now_ms=1000)
        result = self.builder.interact_with_object("tv-1", "watch_video", requester_id="p2", now_ms=1000)
        assert result["payload"]["video"]["videoId"] == "video-2"
        assert result["payload"]["syncSession"]["itemId"] == "video-2"


class TestAiCharacterIntegration:
    def setup_method(self):
        self.builder = RoomBuilderState()
        self.builder.create_object(
            "npc-1", "ai_character", (0, 0), x=10, y=10, width=20, height=20, created_by="alice",
        )

    def test_configure_character_requires_object_to_be_an_ai_character(self):
        self.builder.create_object("table-1", "table", (0, 0), x=50, y=50, width=20, height=20)
        with pytest.raises(ValueError):
            self.builder.configure_character("table-1", name="Owl", role="guide", start_node_id="node-1")

    def test_configure_character_requires_edit_permission(self):
        with pytest.raises(PermissionError):
            self.builder.configure_character(
                "npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="bob",
            )

    def test_configure_character_then_get_character_roundtrips(self):
        self.builder.configure_character(
            "npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice",
        )
        character = self.builder.get_character_config("npc-1")
        assert character["name"] == "Owl"
        assert character["role"] == "guide"

    def test_set_character_knowledge_base_title_requires_edit_permission(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1")
        with pytest.raises(PermissionError):
            self.builder.set_character_knowledge_base_title("npc-1", "Owl Facts", requester_id="bob")

    def test_set_character_knowledge_base_title_updates_character(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        character = self.builder.set_character_knowledge_base_title(
            "npc-1", "Owl Facts", requester_id="alice",
        )
        assert character["knowledgeBase"]["title"] == "Owl Facts"

    def test_add_character_knowledge_document_requires_edit_permission(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1")
        with pytest.raises(PermissionError):
            self.builder.add_character_knowledge_document(
                "npc-1", "doc-1", "Habitat", "text", content="Owls are nocturnal.", requester_id="bob",
            )

    def test_add_character_knowledge_document_updates_character(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        character = self.builder.add_character_knowledge_document(
            "npc-1", "doc-1", "Habitat", "text", content="Owls are nocturnal.", requester_id="alice",
        )
        assert character["knowledgeBase"]["documents"][0]["docId"] == "doc-1"

    def test_remove_character_knowledge_document_requires_edit_permission(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.add_character_knowledge_document(
            "npc-1", "doc-1", "Habitat", "text", content="Owls are nocturnal.", requester_id="alice",
        )
        with pytest.raises(PermissionError):
            self.builder.remove_character_knowledge_document("npc-1", "doc-1", requester_id="bob")

    def test_remove_character_knowledge_document_updates_character(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.add_character_knowledge_document(
            "npc-1", "doc-1", "Habitat", "text", content="Owls are nocturnal.", requester_id="alice",
        )
        character = self.builder.remove_character_knowledge_document("npc-1", "doc-1", requester_id="alice")
        assert character["knowledgeBase"]["documents"] == []

    def test_update_character_knowledge_document_requires_edit_permission(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.add_character_knowledge_document(
            "npc-1", "doc-1", "Habitat", "text", content="Owls are nocturnal.", requester_id="alice",
        )
        with pytest.raises(PermissionError):
            self.builder.update_character_knowledge_document(
                "npc-1", "doc-1", "Habitat 2", "text", content="Updated.", requester_id="bob",
            )

    def test_update_character_knowledge_document_updates_character(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.add_character_knowledge_document(
            "npc-1", "doc-1", "Habitat", "text", content="Owls are nocturnal.", requester_id="alice",
        )
        character = self.builder.update_character_knowledge_document(
            "npc-1", "doc-1", "Habitat 2", "text", content="Updated.", requester_id="alice",
        )
        assert character["knowledgeBase"]["documents"][0]["title"] == "Habitat 2"
        assert character["knowledgeBase"]["documents"][0]["content"] == "Updated."

    def test_configure_generative_mode_enables_only_when_url_and_key_present(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        character = self.builder.configure_character_generative_mode(
            "npc-1", api_base_url="https://api.example.com", api_key="secret",
            requester_id="host-1", is_room_host=True,
        )
        assert character["generativeEnabled"] is True
        assert "apiKey" not in character

    def test_configure_generative_mode_requires_edit_permission(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1")
        with pytest.raises(PermissionError):
            self.builder.configure_character_generative_mode(
                "npc-1", api_base_url="https://api.example.com", api_key="secret", requester_id="bob",
            )

    def test_configure_generative_mode_is_restricted_to_room_host_even_for_object_creator(self):
        # Phase I: AI API settings management is restricted to the room admin
        # (host), not just whoever has object-level edit permission (e.g. the
        # character's creator, if they aren't the room host).
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        with pytest.raises(PermissionError):
            self.builder.configure_character_generative_mode(
                "npc-1", api_base_url="https://api.example.com", api_key="secret",
                requester_id="alice", is_room_host=False,
            )

    def test_configure_generative_mode_succeeds_for_room_host(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        character = self.builder.configure_character_generative_mode(
            "npc-1", api_base_url="https://api.example.com", api_key="secret",
            requester_id="host-1", is_room_host=True,
        )
        assert character["generativeEnabled"] is True

    def test_add_story_node_requires_edit_permission(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1")
        with pytest.raises(PermissionError):
            self.builder.add_story_node("npc-1", "node-1", character_line="Hi", requester_id="bob")

    def test_add_story_node_then_list_story_nodes_roundtrips(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.add_story_node("npc-1", "node-1", character_line="Hi", requester_id="alice")
        assert [n["nodeId"] for n in self.builder.list_story_nodes("npc-1")] == ["node-1"]

    def test_interact_talk_returns_start_node_and_predefined_mode(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.add_story_node(
            "npc-1", "node-1", character_line="Welcome!",
            choices=[{"text": "Continue", "nextNodeId": "node-2"}], requester_id="alice",
        )
        self.builder.add_story_node("npc-1", "node-2", character_line="The end.", requester_id="alice")
        result = self.builder.interact_with_object("npc-1", "talk", requester_id="p1", now_ms=1000)
        assert result["payload"]["node"]["nodeId"] == "node-1"
        assert result["payload"]["mode"] == "predefined"
        assert result["payload"]["character"]["name"] == "Owl"

    def test_talk_to_character_advances_story_with_choice_index(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.add_story_node(
            "npc-1", "node-1", character_line="Welcome!",
            choices=[{"text": "Continue", "nextNodeId": "node-2"}], requester_id="alice",
        )
        self.builder.add_story_node("npc-1", "node-2", character_line="The end.", requester_id="alice")
        self.builder.talk_to_character("npc-1", requester_id="p1")
        result = self.builder.talk_to_character("npc-1", requester_id="p1", choice_index=0)
        assert result["node"]["nodeId"] == "node-2"

    def test_interact_start_mission_resets_story_progress(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.add_story_node(
            "npc-1", "node-1", character_line="Welcome!",
            choices=[{"text": "Continue", "nextNodeId": "node-2"}], requester_id="alice",
        )
        self.builder.add_story_node("npc-1", "node-2", character_line="The end.", requester_id="alice")
        self.builder.talk_to_character("npc-1", requester_id="p1", choice_index=None)
        self.builder.talk_to_character("npc-1", requester_id="p1", choice_index=0)
        result = self.builder.interact_with_object("npc-1", "start_mission", requester_id="p1", now_ms=1000)
        assert result["payload"]["node"]["nodeId"] == "node-1"

    def test_ask_character_falls_back_to_predefined_when_generative_disabled(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        result = self.builder.ask_character("npc-1", requester_id="p1", user_message="hint?", caller=lambda *a: "ignored")
        assert result["mode"] == "predefined"

    def test_ask_character_uses_caller_when_generative_enabled(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.configure_character_generative_mode(
            "npc-1", api_base_url="https://api.example.com", api_key="secret",
            requester_id="host-1", is_room_host=True,
        )
        result = self.builder.ask_character(
            "npc-1", requester_id="p1", user_message="hint?", caller=lambda *a: "A generated hint.",
        )
        assert result["answer"] == "A generated hint."
        assert result["mode"] == "generative"

    def test_interact_talk_raises_key_error_when_character_not_configured(self):
        # Regression guard: a learner clicking "Talk" on an ai_character object
        # that a builder placed but never configured must fail loudly with a
        # KeyError (caught and surfaced as a friendly `error` event by the
        # room:object:interact socket handler), not silently succeed or crash
        # with an unrelated exception type.
        with pytest.raises(KeyError):
            self.builder.interact_with_object("npc-1", "talk", requester_id="p1", now_ms=1000)

    def test_ask_character_raises_key_error_when_character_not_configured(self):
        with pytest.raises(KeyError):
            self.builder.ask_character("npc-1", requester_id="p1", user_message="hint?", caller=lambda *a: "x")

    def test_ask_character_is_rate_limited_per_user_when_generative_enabled(self):
        self.builder.configure_character("npc-1", name="Owl", role="guide", start_node_id="node-1", requester_id="alice")
        self.builder.configure_character_generative_mode(
            "npc-1", api_base_url="https://api.example.com", api_key="secret",
            requester_id="host-1", is_room_host=True,
        )
        caller = lambda *a: "A generated hint."

        for i in range(5):
            result = self.builder.ask_character("npc-1", requester_id="p1", user_message="hint?", caller=caller, now_ms=i)
            assert result["mode"] == "generative"

        blocked = self.builder.ask_character("npc-1", requester_id="p1", user_message="hint?", caller=caller, now_ms=5)
        assert blocked["mode"] == "rate_limited"

