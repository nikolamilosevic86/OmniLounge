import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://omnilaunge:omnilaunge@localhost:5432/omnilaunge",
)
PORT = int(os.getenv("PORT", "8000"))
MOVE_SPEED = float(os.getenv("MOVE_SPEED", "4"))
TICK_RATE = float(os.getenv("TICK_RATE", "30"))
BUBBLE_DURATION_MS = 6000
MAX_MESSAGES = 200

# Socket.IO CORS origins. This app has no authentication -- identity is the
# Socket.IO session id -- so a wildcard here lets any website on the internet
# open a connection on a visitor's behalf. Default to local dev origins and
# require deployments to opt in explicitly via ALLOWED_ORIGINS (a
# comma-separated list, or "*" if a fully public server really is intended).
_DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"


def _parse_allowed_origins(raw: str | None) -> str | list[str]:
    value = (raw or "").strip()
    if not value:
        value = _DEFAULT_ALLOWED_ORIGINS
    if value == "*":
        return "*"
    origins = [item.strip() for item in value.split(",") if item.strip()]
    return origins or [item.strip() for item in _DEFAULT_ALLOWED_ORIGINS.split(",")]


ALLOWED_ORIGINS = _parse_allowed_origins(os.getenv("ALLOWED_ORIGINS"))
