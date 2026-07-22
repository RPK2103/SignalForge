"""Shared API-layer dependencies."""

from fastapi import HTTPException, Request


def _normalize_media_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def is_json_media_type(content_type: str) -> bool:
    media_type = _normalize_media_type(content_type)
    if media_type == "application/json":
        return True
    return media_type.startswith("application/") and media_type.endswith("+json")


def require_json_content_type(request: Request) -> None:
    """Reject requests whose Content-Type is not a JSON media type."""
    raw = request.headers.get("content-type")
    if not raw or not is_json_media_type(raw):
        raise HTTPException(
            status_code=415,
            detail=(
                "Request body must use Content-Type application/json "
                "or a structured JSON media type."
            ),
        )
