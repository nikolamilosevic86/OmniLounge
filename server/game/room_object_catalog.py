"""Phase E: catalog of buildable object types.

Defines, for each object type the room builder supports:
- its authoring category (static "furniture" vs "interactive"),
- default/available size presets,
- and its contextual interaction menu (per design doc section 11.2).

Static furniture (table/chair/bar/sofa) is primarily about world
readability, but still offers simple "sit"-style interactions, mirroring
the existing hardcoded lobby room objects in `client/js/room-objects.js`.
Interactive furniture (bookshelf/tv/music_player) exposes menu actions
that later phases (F/G) wire up to real reading/watch/listen content.
"""

from typing import Any

SIZE_PRESETS: dict[str, tuple[float, float]] = {
    # Scaled so builder-placed furniture reads as proportionate to the
    # player avatar's on-screen footprint (72x108px, see
    # client/css/styles.css `.room-player .avatar-svg`) instead of looking
    # like tiny squares next to a full-size avatar: M matches the avatar's
    # width, and L comfortably exceeds it for "big" furniture (sofas/bars).
    "S": (48.0, 48.0),
    "M": (72.0, 72.0),
    "L": (108.0, 108.0),
}

# AI characters are rendered client-side as a DOM avatar overlay (same shape
# as a player, see client/js/main.js's renderAiCharacters()) at a fixed size
# no matter which size preset is requested, so their collision/interaction
# footprint must match that fixed avatar footprint rather than the generic
# square S/M/L presets above -- otherwise a player could stand on/inside the
# visible character without colliding, and its clickable area wouldn't line
# up with what's drawn on screen.
AI_CHARACTER_FOOTPRINT: tuple[float, float] = (72.0, 108.0)

COLOR_PRESETS: tuple[str, ...] = (
    "natural-wood",
    "dark-wood",
    "white",
    "black",
    "navy",
    "forest-green",
    "burgundy",
    "gold-accent",
)

MATERIAL_PRESETS: tuple[str, ...] = ("wood", "metal", "fabric", "glass", "stone")

_SIT_INTERACTION = {"interactionType": "sit", "label": "Sit down", "actionState": "sitting"}

OBJECT_TYPE_CATALOG: dict[str, dict[str, Any]] = {
    "table": {
        "category": "furniture",
        "defaultSizePreset": "M",
        "interactions": [
            {"interactionType": "gather", "label": "Gather around", "actionState": None},
        ],
    },
    "chair": {
        "category": "furniture",
        "defaultSizePreset": "S",
        "interactions": [dict(_SIT_INTERACTION)],
    },
    "bar": {
        "category": "furniture",
        "defaultSizePreset": "L",
        "interactions": [dict(_SIT_INTERACTION)],
    },
    "sofa": {
        "category": "furniture",
        "defaultSizePreset": "L",
        "interactions": [
            dict(_SIT_INTERACTION),
            {"interactionType": "lounge", "label": "Lounge", "actionState": "lounging"},
        ],
    },
    "bookshelf": {
        "category": "interactive",
        "defaultSizePreset": "M",
        "interactions": [
            {"interactionType": "browse_books", "label": "Browse Books", "actionState": None},
            {"interactionType": "resume_reading", "label": "Continue Reading", "actionState": None},
        ],
    },
    "tv": {
        "category": "interactive",
        "defaultSizePreset": "M",
        "interactions": [
            {"interactionType": "watch_video", "label": "Watch Lesson", "actionState": None},
            {"interactionType": "open_playlist", "label": "Open Playlist", "actionState": None},
        ],
    },
    "music_player": {
        "category": "interactive",
        "defaultSizePreset": "S",
        "interactions": [
            {"interactionType": "play_track", "label": "Play Track", "actionState": None},
            {"interactionType": "view_playlist", "label": "View Playlist", "actionState": None},
        ],
    },
    "ai_character": {
        "category": "interactive",
        "defaultSizePreset": "S",
        "interactions": [
            {"interactionType": "talk", "label": "Talk", "actionState": None},
            {"interactionType": "ask_hint", "label": "Ask Hint", "actionState": None},
            {"interactionType": "start_mission", "label": "Start Mission", "actionState": None},
        ],
    },
    # Escape room feature (design doc §5.1): the door itself is purely a
    # static catalog entry + config blueprint. Live per-visitor open/closed
    # state is never stored on the object -- it lives in EscapeSessionEngine
    # (see room_builder.py's `_escape` engine), so this entry only needs the
    # single unconditional "attempt_open" interaction.
    "escape_door": {
        "category": "interactive",
        "defaultSizePreset": "M",
        "interactions": [
            {"interactionType": "attempt_open", "label": "Try the Door", "actionState": None},
        ],
    },
    # Escape room feature (design doc §5.2): whether the item is currently
    # revealed/held is per-visitor runtime state on EscapeSessionEngine /
    # InventoryEngine, never stored here -- this entry only needs the single
    # "pick_up" interaction.
    "hidden_item": {
        "category": "interactive",
        "defaultSizePreset": "S",
        "interactions": [
            {"interactionType": "pick_up", "label": "Pick Up", "actionState": None},
        ],
    },
}


def is_valid_object_type(object_type: str) -> bool:
    return object_type in OBJECT_TYPE_CATALOG


def get_catalog_entry(object_type: str) -> dict[str, Any]:
    entry = OBJECT_TYPE_CATALOG.get(object_type)
    if entry is None:
        raise ValueError(f"unknown object type: {object_type}")
    return entry


def resolve_size_preset(object_type: str, preset: str) -> tuple[float, float]:
    get_catalog_entry(object_type)  # validates object_type
    if preset not in SIZE_PRESETS:
        raise ValueError(f"unknown size preset: {preset}")
    if object_type == "ai_character":
        return AI_CHARACTER_FOOTPRINT
    return SIZE_PRESETS[preset]


def get_interaction_menu(object_type: str) -> list[dict[str, Any]]:
    entry = get_catalog_entry(object_type)
    return [dict(item) for item in entry["interactions"]]
