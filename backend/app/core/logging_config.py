"""Logging configuration with optional structured JSON output (Prompt 8).

Extends the Phase 1 text logging with:
- a context filter that injects the current correlation/trace/span IDs;
- an optional JSON formatter (``LOG_FORMAT=json``) for machine-ingestible logs;
- a defensive secret-redaction pass so a stray token/bearer value in a log
  message is never emitted in cleartext.

No bearer token, raw claim, request body, provider output, evidence package or
connector credential is ever logged. Structured fields are limited to safe,
low-cardinality diagnostic values.
"""

from __future__ import annotations

import json
import logging
import re

from app.core.config import Settings
from app.core.logging_context import current_snapshot

SERVICE_FIELD = "service"
ENVIRONMENT_FIELD = "environment"

# Defensive redaction of secret-looking substrings in already-formatted messages.
# This is a safety net; call sites must never pass secrets in the first place.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*"), "bearer [REDACTED]"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]+"), "[REDACTED_JWT]"),
    (
        re.compile(r"(?i)(api[_-]?key|secret|password|token)(\s*[:=]\s*)[^\s,;]+"),
        r"\1\2[REDACTED]",
    ),
)


def redact_secrets(message: str) -> str:
    result = message
    for pattern, replacement in _REDACTIONS:
        result = pattern.sub(replacement, result)
    return result


class ContextFilter(logging.Filter):
    """Attach correlation/trace/span IDs and service metadata to each record."""

    def __init__(self, *, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        snapshot = current_snapshot()
        record.correlation_id = snapshot.correlation_id or "-"
        record.trace_id = snapshot.trace_id or "-"
        record.span_id = snapshot.span_id or "-"
        record.service = self._service
        record.environment = self._environment
        return True


class JsonFormatter(logging.Formatter):
    """Emit each record as a single safe JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        message = redact_secrets(record.getMessage())
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "severity": record.levelname,
            "event": record.name,
            "message": message,
            "service": getattr(record, "service", "signalforge"),
            "environment": getattr(record, "environment", "unknown"),
            "correlation_id": getattr(record, "correlation_id", "-"),
            "trace_id": getattr(record, "trace_id", "-"),
            "span_id": getattr(record, "span_id", "-"),
        }
        # Whitelisted safe structured extras only.
        for key in ("route", "method", "status_family", "outcome", "error_category"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"))


class TextFormatter(logging.Formatter):
    """Human-readable text with redaction and correlation context."""

    def format(self, record: logging.LogRecord) -> str:
        original = record.getMessage()
        record.msg = redact_secrets(original)
        record.args = None
        return super().format(record)


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    handler = logging.StreamHandler()
    handler.addFilter(
        ContextFilter(service=settings.otel_service_name, environment=settings.app_env)
    )
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            TextFormatter(
                fmt=(
                    "%(asctime)s %(levelname)s %(name)s "
                    "[cid=%(correlation_id)s trace=%(trace_id)s] %(message)s"
                )
            )
        )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_startup(settings: Settings, *, dashboard_dir: str) -> None:
    logger = logging.getLogger("signalforge.startup")
    snapshot = settings.startup_snapshot()
    logger.info("SignalForge API starting")
    logger.info("app_env=%s log_level=%s", snapshot["app_env"], snapshot["log_level"])
    logger.info("database_configured=%s", snapshot["database_configured"])
    logger.info("cors_origins=%s", snapshot["cors_origins"])
    logger.info(
        "ai_enabled=%s azure_openai_configured=%s api_version=%s",
        snapshot["ai_enabled"],
        snapshot["azure_openai_configured"],
        snapshot["azure_openai_api_version"],
    )
    logger.info(
        "observability_enabled=%s otel_exporter_mode=%s log_format=%s",
        snapshot["observability_enabled"],
        snapshot["otel_exporter_mode"],
        snapshot["log_format"],
    )
    logger.info("dashboard_dir=%s", dashboard_dir)
