"""Connector error taxonomy — stable categories, never leak secrets."""

from __future__ import annotations

import re
from typing import Any

from app.domain.enterprise_enums import ConnectorErrorCategory

_SECRET_MARKERS = (
    "password=",
    "token=",
    "secret=",
    "api_key=",
    "authorization:",
    "bearer ",
    "private_key",
)

_TOKEN_LIKE = re.compile(r"(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{8,}")


def sanitize_error_message(message: str | None, *, max_length: int = 1024) -> str:
    """Redact obvious secret material from provider/error messages."""
    if not message:
        return "unknown error"
    text = str(message)
    lowered = text.lower()
    for marker in _SECRET_MARKERS:
        if marker in lowered:
            return "[redacted: potential secret in error message]"
    text = _TOKEN_LIKE.sub("[redacted-token]", text)
    return text[:max_length]


class ConnectorError(Exception):
    """Domain-specific connector failure with a stable category."""

    def __init__(
        self,
        category: ConnectorErrorCategory,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.category = category
        self.retryable = retryable
        self.status_code = status_code
        self.details = details or {}
        safe = sanitize_error_message(message)
        self.safe_message = safe
        super().__init__(safe)

    def __repr__(self) -> str:
        return (
            f"ConnectorError(category={self.category.value!r}, "
            f"retryable={self.retryable}, status_code={self.status_code})"
        )


def map_http_status_to_error(
    status_code: int,
    *,
    message: str,
    rate_limit_proven: bool = False,
) -> ConnectorError:
    """Map provider HTTP status to a connector error category."""
    if status_code == 401:
        return ConnectorError(
            ConnectorErrorCategory.AUTHENTICATION_ERROR,
            message,
            retryable=False,
            status_code=status_code,
        )
    if status_code == 403 and rate_limit_proven:
        return ConnectorError(
            ConnectorErrorCategory.RATE_LIMITED,
            message,
            retryable=True,
            status_code=status_code,
        )
    if status_code == 403:
        return ConnectorError(
            ConnectorErrorCategory.PERMISSION_DENIED,
            message,
            retryable=False,
            status_code=status_code,
        )
    if status_code == 404:
        return ConnectorError(
            ConnectorErrorCategory.REPOSITORY_NOT_FOUND,
            message,
            retryable=False,
            status_code=status_code,
        )
    if status_code in (409, 422):
        return ConnectorError(
            ConnectorErrorCategory.INVALID_CONFIGURATION,
            message,
            retryable=False,
            status_code=status_code,
        )
    if status_code == 429:
        return ConnectorError(
            ConnectorErrorCategory.RATE_LIMITED,
            message,
            retryable=True,
            status_code=status_code,
        )
    if 500 <= status_code <= 599:
        return ConnectorError(
            ConnectorErrorCategory.PROVIDER_UNAVAILABLE,
            message,
            retryable=True,
            status_code=status_code,
        )
    if 400 <= status_code <= 499:
        return ConnectorError(
            ConnectorErrorCategory.INVALID_CONFIGURATION,
            message,
            retryable=False,
            status_code=status_code,
        )
    return ConnectorError(
        ConnectorErrorCategory.UNKNOWN_CONNECTOR_ERROR,
        message,
        retryable=False,
        status_code=status_code,
    )
