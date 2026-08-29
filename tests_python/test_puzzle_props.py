"""Puzzle prop shapes: physical escape-room props (cipher box, digital lock,
combination dial, riddle tablet, clue board) that give an otherwise abstract
puzzle a recognizable form in the room.

Design: feature_designs/escape_room_feature_design.md §5.4.

Each prop is a real entry in `OBJECT_TYPE_CATALOG`, so it is placeable from
the builder catalog and rendered on the room canvas like any other object --
props deliberately add no parallel "puzzle object" concept. What makes a prop
special is only that it carries no static interaction of its own: an unbound
prop is scenery, and binding `config.puzzleId` is what grows it a "Solve"
action via the existing `_interactions_for` path (§6.2).
"""

import pytest

from server.game.puzzle_templates import list_templates
from server.game.room_builder import RoomBuilderState
from server.game.room_object_catalog import (
    OBJECT_TYPE_CATALOG,
    PUZZLE_PROP_TYPES,
    SIZE_PRESETS,
    get_interaction_menu,
    is_puzzle_prop,
    is_valid_object_type,
    resolve_size_preset,
)


class TestPuzzlePropCatalog:
    def test_defines_the_five_named_prop_shapes(self):
        assert set(PUZZLE_PROP_TYPES) == {
            "cipher_box",
            "digital_lock",
            "combination_dial",
            "riddle_tablet",
            "clue_board",
        }

    def test_every_prop_is_a_real_placeable_object_type(self):
        # Props are ordinary catalog entries, not a separate concept -- so
        # create_object/resize/rotate/delete all work on them for free.
        for prop_type in PUZZLE_PROP_TYPES:
            assert is_valid_object_type(prop_type)
            assert prop_type in OBJECT_TYPE_CATALOG

    def test_every_prop_is_interactive_not_static_furniture(self):
        for prop_type in PUZZLE_PROP_TYPES:
            assert OBJECT_TYPE_CATALOG[prop_type]["category"] == "interactive"

    def test_every_prop_has_a_valid_default_size_preset(self):
        for prop_type in PUZZLE_PROP_TYPES:
            preset = OBJECT_TYPE_CATALOG[prop_type]["defaultSizePreset"]
            assert preset in SIZE_PRESETS
            assert resolve_size_preset(prop_type, preset) == SIZE_PRESETS[preset]

    def test_an_unbound_prop_has_no_static_interactions(self):
        # A prop with no puzzle bound is pure scenery. The "Solve" action is
        # appended by RoomBuilderState._interactions_for only when
        # config.puzzleId is set, so a static menu entry here would offer a
        # dead action on an unconfigured prop.
        for prop_type in PUZZLE_PROP_TYPES:
            assert get_interaction_menu(prop_type) == []

    def test_is_puzzle_prop_discriminates_props_from_other_object_types(self):
        assert is_puzzle_prop("cipher_box") is True
        assert is_puzzle_prop("digital_lock") is True
        assert is_puzzle_prop("table") is False
        assert is_puzzle_prop("escape_door") is False
        assert is_puzzle_prop("nope") is False

    def test_props_do_not_collide_with_pre_existing_object_types(self):
        # Guards against a future rename silently turning an existing
        # furniture/escape type into a "prop" and stripping its interactions.
        assert not set(PUZZLE_PROP_TYPES) & {
            "table", "chair", "bar", "sofa", "bookshelf", "tv",
            "music_player", "ai_character", "escape_door", "hidden_item",
        }


class TestTemplatePropPairing:
    def test_every_template_suggests_a_valid_prop_shape(self):
        for template in list_templates():
            assert is_puzzle_prop(template["propType"]), template["templateId"]

    def test_each_archetype_pairs_with_its_thematic_prop(self):
        props = {t["templateId"]: t["propType"] for t in list_templates()}
        assert props == {
            "riddle": "riddle_tablet",
            "cipher": "cipher_box",
            "sequence": "combination_dial",
            "number_lock": "digital_lock",
            "keyword_search": "clue_board",
        }

    def test_prop_pairing_is_one_to_one_so_every_shape_is_reachable(self):
        # If two templates shared a prop, one of the five shapes would never
        # be suggested by any template and would only be findable by hand.
        props = [t["propType"] for t in list_templates()]
        assert sorted(props) == sorted(PUZZLE_PROP_TYPES)


class TestPuzzlePropType:
    """A puzzle records the shape it is meant to wear, so the builder can
    offer/place the matching prop and the room can render it (§5.4)."""

    def setup_method(self):
        self.builder = RoomBuilderState()

    def test_a_puzzle_defaults_to_no_shape_when_hand_authored(self):
        puzzle = self.builder.add_puzzle("p1", prompt="2+2?", answer="4")
        assert puzzle["propType"] is None

    def test_a_puzzle_can_be_given_an_explicit_shape(self):
        puzzle = self.builder.add_puzzle(
            "p1", prompt="2+2?", answer="4", prop_type="digital_lock",
        )
        assert puzzle["propType"] == "digital_lock"

    def test_a_template_supplies_its_paired_shape_automatically(self):
        puzzle = self.builder.add_puzzle("p1", prompt=None, answer="1234", template_id="number_lock")
        assert puzzle["propType"] == "digital_lock"

    def test_an_explicit_shape_overrides_the_templates_default(self):
        # Same "a template is a starting point, not a cage" rule the
        # prompt/hints/matchMode fields already follow.
        puzzle = self.builder.add_puzzle(
            "p1", prompt=None, answer="1234", template_id="number_lock", prop_type="cipher_box",
        )
        assert puzzle["propType"] == "cipher_box"

    def test_rejects_a_shape_that_is_not_a_puzzle_prop(self):
        with pytest.raises(ValueError, match="prop"):
            self.builder.add_puzzle("p1", prompt="2+2?", answer="4", prop_type="table")

    def test_rejects_an_unknown_shape(self):
        with pytest.raises(ValueError, match="prop"):
            self.builder.add_puzzle("p1", prompt="2+2?", answer="4", prop_type="nope")

    def test_a_rejected_shape_leaves_no_dangling_puzzle_behind(self):
        # Validation must happen before PuzzleEngine.add_puzzle, mirroring
        # how unlock_door_id is checked up front.
        with pytest.raises(ValueError):
            self.builder.add_puzzle("p1", prompt="2+2?", answer="4", prop_type="nope")
        assert self.builder.list_puzzles() == []

    def test_prop_type_survives_into_the_public_puzzle_payload(self):
        # The client renders the shape from this payload, so it must ride the
        # answer-stripped public view, not just the internal record.
        self.builder.add_puzzle("p1", prompt="2+2?", answer="4", prop_type="clue_board")
        listed = self.builder.list_puzzles()
        assert listed[0]["propType"] == "clue_board"
        assert "answer" not in listed[0]

    def test_a_prop_object_bound_to_a_puzzle_offers_solve(self):
        # End-to-end: the shape placed in the room is what the player clicks.
        self.builder.add_puzzle("p1", prompt="2+2?", answer="4", prop_type="cipher_box")
        self.builder.create_object(
            "box-1", "cipher_box", (0, 0), x=100, y=100, width=48, height=48,
            config={"puzzleId": "p1"},
        )
        obj = next(o for o in self.builder.list_objects() if o["objectId"] == "box-1")
        assert [i["interactionType"] for i in obj["interactions"]] == ["solve_puzzle"]

    def test_an_unbound_prop_object_offers_nothing(self):
        self.builder.create_object(
            "box-1", "cipher_box", (0, 0), x=100, y=100, width=48, height=48,
        )
        obj = next(o for o in self.builder.list_objects() if o["objectId"] == "box-1")
        assert obj["interactions"] == []

