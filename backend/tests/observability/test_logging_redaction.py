"""Structured logging + secret-redaction tests (Phase 3 Prompt 8)."""

from __future__ import annotations

import json
import logging

from app.core.logging_config import ContextFilter, JsonFormatter, redact_secrets
from app.core.logging_context import (
    bind_correlation_id,
    bind_trace_context,
    clear_context,
)


def test_redacts_bearer_token():
    out = redact_secrets("Authorization: Bearer abc.def.ghi")
    assert "abc.def.ghi" not in out
    assert "[REDACTED]" in out


def test_redacts_jwt_like_string():
    jwt = "eyJhbGciOi.eyJzdWIiOi.signature123"
    assert jwt not in redact_secrets(f"token={jwt}")


def test_redacts_api_key_assignment():
    out = redact_secrets("api_key=supersecretvalue")
    assert "supersecretvalue" not in out


def test_json_formatter_includes_correlation_and_redacts():
    clear_context()
    bind_correlation_id("corr-123")
    bind_trace_context(trace_id="trace-abc", span_id="span-def")
    record = logging.LogRecord(
        name="signalforge.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login with Bearer leak.token.here",
        args=(),
        exc_info=None,
    )
    ContextFilter(service="signalforge", environment="test").filter(record)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["correlation_id"] == "corr-123"
    assert payload["trace_id"] == "trace-abc"
    assert "leak.token.here" not in payload["message"]
    clear_context()
