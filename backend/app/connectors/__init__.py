"""SignalForge connector SDK — provider-neutral evidence ingestion."""

from app.connectors.errors import ConnectorError
from app.connectors.protocol import (
    Connector,
    ConnectorCapabilities,
    ConnectorCheckpointCursor,
    ConnectorContext,
    ConnectorDescriptor,
    ConnectorPage,
    ConnectorRequest,
    ConnectorStream,
    NormalizedConnectorEvent,
    RateLimitState,
)
from app.connectors.registry import ConnectorRegistry, get_default_registry

__all__ = [
    "Connector",
    "ConnectorCapabilities",
    "ConnectorCheckpointCursor",
    "ConnectorContext",
    "ConnectorDescriptor",
    "ConnectorError",
    "ConnectorPage",
    "ConnectorRequest",
    "ConnectorStream",
    "NormalizedConnectorEvent",
    "RateLimitState",
    "ConnectorRegistry",
    "get_default_registry",
]
