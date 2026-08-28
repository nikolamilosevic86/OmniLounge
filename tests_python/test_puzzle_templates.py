"""Phase 3: puzzle template library (design doc
feature_designs/escape_room_feature_design.md §14 Phase 3, §16 Q5).

Pre-built puzzle archetypes (riddle / cipher / sequence / number-lock /
keyword-search) that pre-fill a creator's prompt, hints and -- crucially --
the correct `match_mode` preset, so authors stop having to reason about
which match mode a given puzzle shape needs.
"""

import pytest

from server.game.puzzle import MATCH_MODES
from server.game.puzzle_templates import (
    PUZZLE_TEMPLATES,
    build_puzzle_from_template,
    get_template,
    list_templates,
)


class TestTemplateCatalog:
    def test_lists_every_template(self):
        templates = list_templates()
        assert len(templates) == len(PUZZLE_TEMPLATES)
        assert {t["templateId"] for t in templates} == set(PUZZLE_TEMPLATES)

    def test_covers_the_archetypes_named_in_the_design_doc(self):
        ids = {t["templateId"] for t in list_templates()}
        assert {"riddle", "cipher", "sequence"} <= ids

    def test_every_template_has_creator_facing_authoring_fields(self):
        for template in list_templates():
            assert template["label"]
            assert template["description"]
            assert template["promptTemplate"]
            assert template["answerPlaceholder"]
            assert isinstance(template["hints"], list)

    def test_every_template_uses_a_valid_match_mode_preset(self):
        for template in list_templates():
            assert template["matchMode"] in MATCH_MODES

    def test_number_lock_template_presets_numeric_matching(self):
        # The whole point of the presets: a creator picking "number lock"
        # should not have to know that free-text matching would reject "007"
        # for an answer of "7".
        assert get_template("number_lock")["matchMode"] == "numeric"

    def test_keyword_search_template_presets_contains_matching(self):
        assert get_template("keyword_search")["matchMode"] == "contains"

    def test_riddle_template_presets_exact_matching(self):
        assert get_template("riddle")["matchMode"] == "exact"

    def test_list_templates_returns_copies_callers_cannot_mutate(self):
        list_templates()[0]["label"] = "hacked"
        assert all(t["label"] != "hacked" for t in list_templates())

    def test_template_hints_are_copies_callers_cannot_mutate(self):
        get_template("riddle")["hints"].append("leaked")
        assert "leaked" not in get_template("riddle")["hints"]

    def test_unknown_template_raises_key_error(self):
        with pytest.raises(KeyError):
            get_template("does-not-exist")


class TestBuildPuzzleFromTemplate:
    """`build_puzzle_from_template` resolves a template into the exact
    keyword arguments `PuzzleEngine.add_puzzle` already accepts, so the
    template library stays a pure authoring-time convenience and adds no
    new concepts to the engine itself."""

    def test_applies_the_templates_match_mode_preset(self):
        fields = build_puzzle_from_template("number_lock", answer="1234")
        assert fields["match_mode"] == "numeric"

    def test_applies_the_templates_prompt_and_hints(self):
        fields = build_puzzle_from_template("riddle", answer="a piano")
        assert fields["prompt"] == get_template("riddle")["promptTemplate"]
        assert fields["hints"] == get_template("riddle")["hints"]

    def test_caller_prompt_overrides_the_template_default(self):
        fields = build_puzzle_from_template("riddle", answer="a piano", prompt="My own riddle")
        assert fields["prompt"] == "My own riddle"

    def test_caller_hints_override_the_template_defaults(self):
        fields = build_puzzle_from_template("riddle", answer="a piano", hints=["mine"])
        assert fields["hints"] == ["mine"]

    def test_caller_match_mode_overrides_the_template_preset(self):
        # The preset is a smart default, not a cage -- a creator can still
        # author a riddle that accepts a keyword anywhere in the answer.
        fields = build_puzzle_from_template("riddle", answer="a piano", match_mode="contains")
        assert fields["match_mode"] == "contains"

    def test_empty_caller_hints_list_overrides_rather_than_falls_back(self):
        # Explicitly clearing the hints must mean "no hints", not "give me
        # the template's hints back".
        fields = build_puzzle_from_template("riddle", answer="a piano", hints=[])
        assert fields["hints"] == []

    def test_answer_is_required(self):
        with pytest.raises(ValueError):
            build_puzzle_from_template("riddle", answer="   ")

    def test_unknown_template_raises_key_error(self):
        with pytest.raises(KeyError):
            build_puzzle_from_template("nope", answer="x")

    def test_returned_hints_are_not_the_catalogs_own_list(self):
        fields = build_puzzle_from_template("riddle", answer="a piano")
        fields["hints"].append("leaked")
        assert "leaked" not in get_template("riddle")["hints"]

    @pytest.mark.parametrize("template_id", sorted(PUZZLE_TEMPLATES))
    def test_every_template_produces_engine_ready_kwargs(self, template_id):
        from server.game.puzzle import PuzzleEngine

        fields = build_puzzle_from_template(template_id, answer="42")
        engine = PuzzleEngine()
        created = engine.add_puzzle("p1", **fields)
        assert created["matchMode"] == fields["match_mode"]
        assert "answer" not in created
