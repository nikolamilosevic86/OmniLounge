import json
from typing import Any

AVATAR_OPTIONS = {
    "skinColors": ["#FFDBAC", "#F1C27D", "#E0AC69", "#C68642", "#8D5524", "#5C3D2E"],
    "gender": ["neutral", "feminine", "masculine"],
    "hair": ["short", "long", "curly", "mohawk", "bald", "ponytail"],
    "beards": ["none", "stubble", "goatee", "full"],
    "glasses": ["none", "round", "square", "sunglasses"],
    "clothes": ["tshirt", "hoodie", "suit", "dress", "jacket"],
    "accessories": ["none", "hat", "backpack", "scarf", "headphones"],
}


def create_default_avatar(username: str) -> dict[str, Any]:
    return create_avatar({"username": username})


def create_avatar(options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    return {
        "username": options.get("username", "Guest"),
        "skinColor": options.get("skinColor", AVATAR_OPTIONS["skinColors"][0]),
        "gender": options.get("gender", AVATAR_OPTIONS["gender"][0]),
        "hair": options.get("hair", AVATAR_OPTIONS["hair"][0]),
        "beard": options.get("beard", "none"),
        "glasses": options.get("glasses", "none"),
        "clothes": options.get("clothes", AVATAR_OPTIONS["clothes"][0]),
        "accessory": options.get("accessory", "none"),
    }


def validate_avatar(avatar: dict[str, Any]) -> bool:
    username = avatar.get("username", "")
    if not username or not str(username).strip():
        return False
    if avatar.get("skinColor") not in AVATAR_OPTIONS["skinColors"]:
        return False
    if avatar.get("gender") not in AVATAR_OPTIONS["gender"]:
        return False
    if avatar.get("hair") not in AVATAR_OPTIONS["hair"]:
        return False
    if avatar.get("beard") not in AVATAR_OPTIONS["beards"]:
        return False
    if avatar.get("glasses") not in AVATAR_OPTIONS["glasses"]:
        return False
    if avatar.get("clothes") not in AVATAR_OPTIONS["clothes"]:
        return False
    if avatar.get("accessory") not in AVATAR_OPTIONS["accessories"]:
        return False
    return True


def serialize_avatar(avatar: dict[str, Any]) -> str:
    return json.dumps(avatar)


def deserialize_avatar(data: str) -> dict[str, Any]:
    return json.loads(data)
