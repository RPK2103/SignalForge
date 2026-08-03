"""Centralized telemetry attribute allowlist + redaction policy (Prompt 8).

There is exactly ONE allowlist of low-cardinality attributes that may appear as
metric labels. Everything else is dropped. High-cardinality or sensitive values
(IDs, tenant IDs, correlation IDs, emails, prompts, tokens, exception text …)
are never permitted as metric dimensions. This is the single guard against
metric-cardinality explosions and telemetry data leaks.
"""

from __future__ import annotations

import re
from typing import Any

# The ONLY attributes permitted as exported metric labels. All low-cardinality.
ALLOWED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "service",
        "operation",
        "http_method",
        "route",  # normalized template only (see normalize_route)
        "status_family",  # 2xx/3xx/4xx/5xx
        "status_code",  # bounded set of known codes
        "outcome",  # OperationOutcome value
        "provider_type",
        "fallback_category",
        "connector_type",
        "evaluation_type",
        "model_version",  # bounded, published model version string
        "prompt_template_version",
        "scenario_kind",
        "environment",
        "source_type",
        "freshness_state",
        "slo_status",
        "alert_severity",
    }
)

# Explicitly denied categories — never allowed as metric labels. Documented so
# the policy is auditable and tested. (This is illustrative, not exhaustive: the
# allowlist above is authoritative — anything not on it is dropped.)
DENIED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "url",
        "path",
        "raw_path",
        "request_id",
        "trace_id",
        "correlation_id",
        "tenant_id",
        "principal_id",
        "subject",
        "user",
        "username",
        "email",
        "repository",
        "repo",
        "project",
        "project_name",
        "evidence_id",
        "exception",
        "exception_message",
        "error_message",
        "prompt",
        "prompt_text",
        "token",
        "bearer",
        "authorization",
        "secret",
        "password",
        "api_key",
    }
)

# Bounded set of status codes we are willing to record as a metric dimension.
# Anything else collapses to its status family only.
_KNOWN_STATUS_CODES: frozenset[int] = frozenset(
    {200, 201, 202, 204, 301, 302, 304, 400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504}
)

_MAX_ATTRIBUTE_VALUE_LEN = 64

# Values that look like emails, UUIDs, JWTs, or bearer tokens are never safe to
# export even under an allowlisted key (e.g. model_version="a@b.com").
_REDACTED_VALUE = "redacted"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
_BEARERISH_RE = re.compile(r"^(Bearer\s+)?[A-Za-z0-9_\-]{32,}$")


def status_family(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "2xx"
    if 300 <= status_code < 400:
        return "3xx"
    if 400 <= status_code < 500:
        return "4xx"
    if 500 <= status_code < 600:
        return "5xx"
    return "other"


def bounded_status_code(status_code: int) -> str:
    return str(status_code) if status_code in _KNOWN_STATUS_CODES else status_family(status_code)


def _sanitize_value(text: str, *, max_value_len: int) -> str:
    """Bound length and redact values that look like secrets or identifiers."""
    if (
        "@" in text
        or _EMAIL_RE.match(text)
        or _UUID_RE.match(text)
        or _JWT_RE.match(text)
        or (len(text) >= 32 and _BEARERISH_RE.match(text))
    ):
        return _REDACTED_VALUE
    if len(text) > max_value_len:
        return text[:max_value_len]
    return text


class TelemetryAttributePolicy:
    """Filters and bounds attributes before they become metric labels."""

    def __init__(
        self,
        allowed: frozenset[str] = ALLOWED_ATTRIBUTES,
        *,
        max_value_len: int = _MAX_ATTRIBUTE_VALUE_LEN,
    ) -> None:
        self._allowed = allowed
        self._max_value_len = max_value_len

    def is_allowed(self, key: str) -> bool:
        return key in self._allowed

    def sanitize(self, attributes: dict[str, Any] | None) -> dict[str, str]:
        """Return only allowlisted, bounded, string-coerced attributes.

        Nested structures and disallowed keys are dropped entirely. This runs on
        every metric emission, so an accidental sensitive attribute (e.g. a
        tenant_id or a nested secret) can never reach the exporter. Dangerous
        *values* under allowlisted keys (email, UUID, JWT, token-like) are
        replaced with ``redacted``.
        """
        if not attributes:
            return {}
        clean: dict[str, str] = {}
        for key, value in attributes.items():
            if key not in self._allowed:
                continue
            if value is None:
                continue
            if isinstance(value, (dict, list, tuple, set, bytes)):
                # Never allow structured/binary values as labels.
                continue
            text = str(value)
            clean[key] = _sanitize_value(text, max_value_len=self._max_value_len)
        return clean
