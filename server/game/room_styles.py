"""Phase K+: the 5 selectable "empty room" visual styles a user can choose
from when creating a custom room.

Kept in sync with `client/js/room-styles.js` / `src/room-styles.js`, which
own the actual color presets used for rendering. This server-side module
only needs to validate/normalize the style id a client sends on
`room:create`, so it doesn't duplicate rendering colors.
"""

ROOM_STYLE_IDS: tuple[str, ...] = (
    "modern-loft",
    "cozy-den",
    "sunlit-studio",
    "midnight-lounge",
    "minimalist-white",
)

DEFAULT_ROOM_STYLE = "modern-loft"


def is_valid_room_style(style_id: str | None) -> bool:
    return style_id in ROOM_STYLE_IDS


def resolve_room_style(style_id: str | None) -> str:
    return style_id if is_valid_room_style(style_id) else DEFAULT_ROOM_STYLE
