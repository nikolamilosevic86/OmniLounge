import pytest

from server.game.room_object_catalog import (
    AI_CHARACTER_FOOTPRINT,
    COLOR_PRESETS,
    MATERIAL_PRESETS,
    OBJECT_TYPE_CATALOG,
    SIZE_PRESETS,
    get_catalog_entry,
    get_interaction_menu,
    is_valid_object_type,
    resolve_size_preset,
)


class TestObjectTypeCatalog:
    def test_all_phase_e_object_types_are_defined(self):
        expected = {"table", "chair", "bar", "sofa", "bookshelf", "tv", "music_player"}
        assert expected.issubset(OBJECT_TYPE_CATALOG.keys())

    def test_is_valid_object_type(self):
        assert is_valid_object_type("bookshelf") is True
        assert is_valid_object_type("spaceship") is False

    def test_get_catalog_entry_rejects_unknown_type(self):
        with pytest.raises(ValueError):
            get_catalog_entry("spaceship")

    def test_static_furniture_has_atmosphere_interactions(self):
        assert get_catalog_entry("chair")["category"] == "furniture"
        assert get_catalog_entry("sofa")["interactions"][0]["interactionType"] == "sit"

    def test_interactive_furniture_has_content_interactions(self):
        assert get_catalog_entry("bookshelf")["category"] == "interactive"
        types = {i["interactionType"] for i in get_catalog_entry("tv")["interactions"]}
        assert types == {"watch_video", "open_playlist"}


class TestSizePresets:
    def test_resolve_size_preset_returns_dimensions(self):
        assert resolve_size_preset("table", "M") == SIZE_PRESETS["M"]

    def test_resolve_size_preset_rejects_unknown_preset(self):
        with pytest.raises(ValueError):
            resolve_size_preset("table", "XL")

    def test_resolve_size_preset_rejects_unknown_object_type(self):
        with pytest.raises(ValueError):
            resolve_size_preset("spaceship", "M")

    def test_size_presets_are_proportionate_to_avatar_footprint(self):
        # Regression test: SIZE_PRESETS used to be tiny (32/48/72px squares)
        # next to the ~72x108px on-screen avatar footprint (see
        # client/css/styles.css `.room-player .avatar-svg`), making builder
        # furniture look disproportionately small next to a player. M should
        # be at least as wide as the avatar, and presets must scale S < M < L.
        avatar_width, avatar_height = 72.0, 108.0
        assert SIZE_PRESETS["S"][0] < SIZE_PRESETS["M"][0] < SIZE_PRESETS["L"][0]
        assert SIZE_PRESETS["M"][0] >= avatar_width
        assert SIZE_PRESETS["L"][1] >= avatar_height * 0.9

    @pytest.mark.parametrize("preset", ["S", "M", "L"])
    def test_ai_character_always_resolves_to_fixed_avatar_footprint(self, preset):
        # AI characters render client-side as a fixed-size DOM avatar overlay
        # regardless of size preset (see client/js/main.js's
        # renderAiCharacters()), so their collision/click footprint must
        # always match that fixed avatar size -- not the generic square
        # S/M/L furniture presets -- no matter which preset is requested.
        assert resolve_size_preset("ai_character", preset) == AI_CHARACTER_FOOTPRINT

    def test_ai_character_footprint_matches_avatar_dimensions(self):
        assert AI_CHARACTER_FOOTPRINT == (72.0, 108.0)


class TestInteractionMenu:
    def test_get_interaction_menu_returns_copy_not_shared_reference(self):
        menu = get_interaction_menu("sofa")
        menu[0]["label"] = "mutated"
        assert get_interaction_menu("sofa")[0]["label"] == "Sit down"

    def test_get_interaction_menu_rejects_unknown_type(self):
        with pytest.raises(ValueError):
            get_interaction_menu("spaceship")


class TestStylePresets:
    def test_color_and_material_presets_are_non_empty(self):
        assert len(COLOR_PRESETS) > 0
        assert len(MATERIAL_PRESETS) > 0
