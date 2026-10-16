"""Application error codes and the exception that carries them to the API layer."""

from __future__ import annotations

from typing import Any

# Explicit codes from the roadmap (section 14) plus two generic ones.
GEOCODER_NOT_CONFIGURED = "GEOCODER_NOT_CONFIGURED"
GEOCODER_UNAVAILABLE = "GEOCODER_UNAVAILABLE"
ADDRESS_AMBIGUOUS = "ADDRESS_AMBIGUOUS"
OUTSIDE_SERVICE_AREA = "OUTSIDE_SERVICE_AREA"
ROUTER_UNAVAILABLE = "ROUTER_UNAVAILABLE"
CAMERA_DATA_UNAVAILABLE = "CAMERA_DATA_UNAVAILABLE"
STALE_SNAPSHOT = "STALE_SNAPSHOT"
NO_DRIVABLE_ROUTE = "NO_DRIVABLE_ROUTE"
NO_IMPROVED_CANDIDATE = "NO_IMPROVED_CANDIDATE"
ASSESSMENT_INCOMPLETE = "ASSESSMENT_INCOMPLETE"
SEARCH_BUDGET_EXCEEDED = "SEARCH_BUDGET_EXCEEDED"
VALIDATION_ERROR = "VALIDATION_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"

DEFAULT_HTTP_STATUS: dict[str, int] = {
    GEOCODER_NOT_CONFIGURED: 503,
    GEOCODER_UNAVAILABLE: 503,
    ADDRESS_AMBIGUOUS: 409,
    OUTSIDE_SERVICE_AREA: 422,
    ROUTER_UNAVAILABLE: 503,
    CAMERA_DATA_UNAVAILABLE: 503,
    STALE_SNAPSHOT: 200,
    NO_DRIVABLE_ROUTE: 422,
    NO_IMPROVED_CANDIDATE: 200,
    ASSESSMENT_INCOMPLETE: 200,
    SEARCH_BUDGET_EXCEEDED: 200,
    VALIDATION_ERROR: 400,
    INTERNAL_ERROR: 500,
}


class AppError(Exception):
    """An error with a stable machine-readable code. Messages must never contain trip data."""

    def __init__(self, code: str, message: str, *, http_status: int | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status or DEFAULT_HTTP_STATUS.get(code, 400)
        self.details = details or {}
