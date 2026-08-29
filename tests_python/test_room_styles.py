from server.game.room_styles import (
    ROOM_STYLE_IDS,
    DEFAULT_ROOM_STYLE,
    is_valid_room_style,
    resolve_room_style,
)


class TestRoomStyleIds:
    def test_has_exactly_8_styles(self):
        assert len(ROOM_STYLE_IDS) == 8

    def test_ids_are_unique(self):
        assert len(set(ROOM_STYLE_IDS)) == len(ROOM_STYLE_IDS)

    def test_default_style_is_one_of_the_ids(self):
        assert DEFAULT_ROOM_STYLE in ROOM_STYLE_IDS


class TestIsValidRoomStyle:
    def test_true_for_every_known_id(self):
        for style_id in ROOM_STYLE_IDS:
            assert is_valid_room_style(style_id) is True

    def test_false_for_unknown_id(self):
        assert is_valid_room_style("haunted-mansion") is False

    def test_false_for_none_or_empty(self):
        assert is_valid_room_style(None) is False
        assert is_valid_room_style("") is False


class TestResolveRoomStyle:
    def test_returns_known_id_unchanged(self):
        style_id = next(iter(ROOM_STYLE_IDS))
        assert resolve_room_style(style_id) == style_id

    def test_falls_back_to_default_for_unknown_id(self):
        assert resolve_room_style("haunted-mansion") == DEFAULT_ROOM_STYLE

    def test_falls_back_to_default_for_none(self):
        assert resolve_room_style(None) == DEFAULT_ROOM_STYLE
