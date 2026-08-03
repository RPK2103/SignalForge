"""Shared correlation-ID contract (Phase 3 Prompt 8).

One definition of the correlation header and the sanitization rules so the
authentication middleware, telemetry middleware, CORS config, exception handlers
and structured logging all agree. Correlation IDs are safe, bounded, opaque
diagnostic identifiers — never secrets and never tenant/principal identifiers.
"""

from __future__ import annotations

import re
import uuid

CORRELATION_HEADER = "X-Correlation-ID"
TRACEPARENT_HEADER = "traceparent"

# Correlation IDs are bounded and restricted to a safe character set so an
# oversized or injected value can never poison logs, metrics labels or headers.
_MAX_CORRELATION_LEN = 128
_SAFE_CORRELATION = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# W3C traceparent: version "-" trace-id(32 hex) "-" parent-id(16 hex) "-" flags(2 hex)
_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


def generate_correlation_id() -> str:
    return uuid.uuid4().hex


def sanitize_correlation_id(raw: str | None) -> str:
    """Return a safe correlation ID, generating one when absent/invalid.

    Oversized or invalid inbound correlation IDs are rejected (a fresh one is
    generated) rather than trusted, so a caller cannot inject unbounded or
    unsafe values into telemetry.
    """
    if not raw:
        return generate_correlation_id()
    candidate = raw.strip()
    if not candidate or len(candidate) > _MAX_CORRELATION_LEN:
        return generate_correlation_id()
    if not _SAFE_CORRELATION.match(candidate):
        return generate_correlation_id()
    return candidate


def parse_traceparent(raw: str | None) -> tuple[str, str] | None:
    """Return (trace_id, parent_span_id) from a valid W3C traceparent, else None."""
    if not raw:
        return None
    candidate = raw.strip().lower()
    if not _TRACEPARENT.match(candidate):
        return None
    parts = candidate.split("-")
    trace_id, parent_id = parts[1], parts[2]
    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return None
    return trace_id, parent_id
