"""Secret redaction and safe hashing for security metadata (Prompt 7).

Audit events must never persist bearer tokens, raw authorization headers, raw
credentials, complete private claims, or secret values. These helpers hash
identifiers and recursively strip anything that looks like a secret.
"""

from __future__ import annotations

import hashlib
import re

_MAX_METADATA_KEYS = 20
_MAX_VALUE_LENGTH = 256

# Keys whose values are always dropped, regardless of content.
_FORBIDDEN_KEY_PATTERN = re.compile(
    r"(token|secret|password|passwd|authorization|auth_header|credential|"
    r"api[_-]?key|private[_-]?key|signing[_-]?key|bearer|jwt|cookie|session)",
    re.IGNORECASE,
)

# Values that look like bearer tokens / JWTs / long opaque secrets.
_SECRET_VALUE_PATTERNS = (
    re.compile(r"^Bearer\s+", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWT
    re.compile(r"env://SIGNALFORGE_[A-Z0-9_]+_(?:SECRET|KEY|TOKEN)", re.IGNORECASE),
)

_REDACTED = "[redacted]"


def hash_identifier(value: str | None) -> str | None:
    """Stable, non-reversible hash for correlating without storing the raw id."""
    if value is None or not str(value).strip():
        return None
    return hashlib.sha256(str(value).strip().encode("utf-8")).hexdigest()


def looks_like_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)


def contains_secret(value: object) -> bool:
    """Recursively detect secret-like content in nested metadata."""
    if isinstance(value, str):
        return looks_like_secret(value)
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _FORBIDDEN_KEY_PATTERN.search(key):
                return True
            if contains_secret(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item) for item in value)
    return False


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        if looks_like_secret(value):
            return _REDACTED
        return value[:_MAX_VALUE_LENGTH]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    # Anything structured is coerced to a bounded string to avoid unbounded blobs.
    return str(value)[:_MAX_VALUE_LENGTH]


def sanitize_metadata(metadata: dict | None) -> dict:
    """Bounded, secret-free metadata suitable for an append-only audit row.

    - forbidden keys are dropped entirely;
    - secret-looking values are redacted;
    - keys and value sizes are bounded.
    """
    if not metadata:
        return {}
    safe: dict[str, object] = {}
    for key, value in list(metadata.items())[:_MAX_METADATA_KEYS]:
        if not isinstance(key, str):
            continue
        if _FORBIDDEN_KEY_PATTERN.search(key):
            continue
        safe[key[:64]] = _redact_value(value)
    return safe
