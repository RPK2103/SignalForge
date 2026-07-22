"""Shared OpenAPI response declarations."""

from app.core.exceptions import APIErrorResponse

JSON_BODY_ERROR_RESPONSES: dict[int, dict] = {
    415: {
        "model": APIErrorResponse,
        "description": (
            "Unsupported media type — request body must use "
            "application/json or a structured JSON media type"
        ),
    },
    422: {
        "model": APIErrorResponse,
        "description": "Request validation failed",
    },
}
