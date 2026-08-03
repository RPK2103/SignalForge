"""Provider-independent observability boundary (Phase 3 Prompt 8).

Domain services depend only on the :class:`ObservabilityProvider` protocol and the
centralized :class:`TelemetryAttributePolicy`. Concrete providers (no-op,
in-memory, OpenTelemetry) are wired at the application edge. Telemetry failure
never alters deterministic scoring and never bypasses security.
"""

from app.observability.attributes import (
    ALLOWED_ATTRIBUTES,
    DENIED_ATTRIBUTES,
    TelemetryAttributePolicy,
    status_family,
)
from app.observability.metrics import MetricName, OperationOutcome, SpanStatus
from app.observability.provider import (
    InMemoryObservabilityProvider,
    MetricPoint,
    NoOpObservabilityProvider,
    ObservabilityProvider,
    OperationContext,
    TraceContext,
)
from app.observability.runtime import (
    get_observability_provider,
    reset_observability_provider,
    set_observability_provider,
)

__all__ = [
    "ALLOWED_ATTRIBUTES",
    "DENIED_ATTRIBUTES",
    "TelemetryAttributePolicy",
    "status_family",
    "MetricName",
    "OperationOutcome",
    "SpanStatus",
    "MetricPoint",
    "ObservabilityProvider",
    "NoOpObservabilityProvider",
    "InMemoryObservabilityProvider",
    "OperationContext",
    "TraceContext",
    "get_observability_provider",
    "set_observability_provider",
    "reset_observability_provider",
]
