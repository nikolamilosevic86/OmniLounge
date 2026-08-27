import pytest

from server.game.avatar import (
    AVATAR_OPTIONS,
    create_avatar,
    create_default_avatar,
    create_default_character_appearance,
    deserialize_avatar,
    serialize_avatar,
    validate_avatar,
    validate_character_appearance,
)


class TestAvatar:
    def test_create_default_avatar(self):
        avatar = create_default_avatar("Player1")
        assert avatar["username"] == "Player1"
        assert avatar["skinColor"] == AVATAR_OPTIONS["skinColors"][0]
        assert avatar["beard"] == "none"

    def test_create_custom_avatar(self):
        avatar = create_avatar({
            "username": "CoolUser",
            "skinColor": "#8D5524",
            "hair": "mohawk",
            "beard": "full",
            "glasses": "round",
            "clothes": "suit",
            "accessory": "hat",
        })
        assert avatar["username"] == "CoolUser"
        assert avatar["hair"] == "mohawk"

    def test_validate_avatar(self):
        assert validate_avatar(create_default_avatar("Valid")) is True
        assert validate_avatar(create_default_avatar("")) is False
        assert validate_avatar(create_avatar({"username": "X", "hair": "unicorn"})) is False

    def test_serialization_roundtrip(self):
        original = create_avatar({"username": "Test", "hair": "curly"})
        restored = deserialize_avatar(serialize_avatar(original))
        assert restored == original


class TestCharacterAppearance:
    """AI-character appearance reuses the same option set as player avatars,
    minus the username, so characters can be rendered in the avatar shape
    and customized the same way."""

    def test_create_default_character_appearance_has_no_username(self):
        appearance = create_default_character_appearance()
        assert "username" not in appearance
        assert appearance["skinColor"] == AVATAR_OPTIONS["skinColors"][0]
        assert appearance["beard"] == "none"

    def test_validate_character_appearance_accepts_defaults(self):
        assert validate_character_appearance(create_default_character_appearance()) is True

    def test_validate_character_appearance_rejects_unknown_value(self):
        appearance = create_default_character_appearance()
        appearance["hair"] = "unicorn"
        assert validate_character_appearance(appearance) is False

    def test_validate_character_appearance_does_not_require_username(self):
        # Unlike validate_avatar, appearance validation has no username field.
        appearance = create_default_character_appearance()
        assert "username" not in appearance
        assert validate_character_appearance(appearance) is True
