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
