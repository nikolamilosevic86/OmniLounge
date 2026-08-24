import pytest

from server.game.avatar import (
    AVATAR_OPTIONS,
    create_avatar,
    create_default_avatar,
    deserialize_avatar,
    serialize_avatar,
    validate_avatar,
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
