"""Standard error envelope for auth HTTP endpoints (design doc §7.1.x).

All auth error responses share `{"error": CODE, "message": ..., "details": {}}`
regardless of which endpoint raised them, via a single exception type and
FastAPI exception handler registered once in server/main.py.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class AuthHTTPError(Exception):
    def __init__(self, status_code: int, error: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details or {}


async def auth_http_error_handler(request: Request, exc: AuthHTTPError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "message": exc.message, "details": exc.details},
    )
