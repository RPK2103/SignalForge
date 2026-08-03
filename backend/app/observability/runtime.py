"""Process-wide observability provider accessor (Prompt 8).

A single provider instance is selected at application startup and read by
middleware and domain telemetry helpers. This is intentionally a thin, explicitly
set holder — NOT a global mutable metrics dictionary. Tests install a deterministic
:class:`InMemoryObservabilityProvider` and reset it between cases.
"""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.observability.provider import (
    NoOpObservabilityProvider,
    ObservabilityProvider,
)

_logger = logging.getLogger("signalforge.observability")

_provider: ObservabilityProvider | None = None


def get_observability_provider() -> ObservabilityProvider:
    global _provider
    if _provider is None:
        _provider = NoOpObservabilityProvider()
    return _provider


def set_observability_provider(provider: ObservabilityProvider) -> None:
    global _provider
    _provider = provider


def reset_observability_provider() -> None:
    global _provider
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            _logger.debug("provider shutdown failed", exc_info=True)
    _provider = None


def build_provider(settings: Settings) -> ObservabilityProvider:
    """Select a provider from settings without ever failing core startup.

    - observability disabled -> no-op;
    - exporter mode none -> in-memory (safe local recording, no network);
    - exporter mode console/otlp -> OpenTelemetry provider when the SDK is
      installed, otherwise degrade to in-memory and log a warning.
    """
    if not settings.observability_enabled:
        return NoOpObservabilityProvider()

    from app.observability.provider import InMemoryObservabilityProvider

    if settings.otel_exporter_mode == "none":
        return InMemoryObservabilityProvider()

    try:
        from app.observability.otel import OpenTelemetryObservabilityProvider

        return OpenTelemetryObservabilityProvider(settings)
    except Exception:  # noqa: BLE001 - missing SDK / bad config must not break startup
        _logger.warning(
            "OpenTelemetry provider unavailable (mode=%s); using in-memory telemetry",
            settings.otel_exporter_mode,
        )
        return InMemoryObservabilityProvider()


def init_observability(settings: Settings) -> ObservabilityProvider:
    provider = build_provider(settings)
    set_observability_provider(provider)
    return provider
