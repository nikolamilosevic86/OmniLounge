import pytest

from server.game.room_object_catalog import (
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
