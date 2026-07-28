"""Provider-neutral connector protocol contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enterprise_enums import DataSourceType, PermissionClassification
from app.domain.tenant_context import TenantContext


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectorCapabilities(_Strict):
    supports_initial_sync: bool = True
    supports_incremental_sync: bool = True
    supports_unauthenticated: bool = False
    requires_credential_reference: bool = False
    supports_webhooks: bool = False
    operational: bool = True


class ConnectorStream(_Strict):
    name: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    supports_incremental: bool = True
    default_page_size: int = Field(default=30, ge=1, le=100)


class ConnectorDescriptor(_Strict):
    connector_key: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    source_type: DataSourceType
    streams: list[ConnectorStream] = Field(default_factory=list)
    capabilities: ConnectorCapabilities = Field(default_factory=ConnectorCapabilities)
    config_schema_version: str = "1"
    documentation_notes: str | None = Field(default=None, max_length=1024)


@dataclass(frozen=True, slots=True)
class ConnectorContext:
    tenant: TenantContext
    data_source_id: str
    correlation_id: str
    credential_token: str | None = None
    max_pages: int | None = None

    def __repr__(self) -> str:
        return (
            f"ConnectorContext(tenant_id={self.tenant.tenant_id!r}, "
            f"data_source_id={self.data_source_id!r}, "
            f"correlation_id={self.correlation_id!r}, "
            f"has_credential={self.credential_token is not None})"
        )


class ConnectorCheckpointCursor(_Strict):
    """Provider-neutral next-checkpoint candidate (not yet durable)."""

    schema_version: str = "1"
    payload: dict[str, Any] = Field(default_factory=dict)
    high_watermark_time: datetime | None = None
    high_watermark_source_id: str | None = Field(default=None, max_length=256)
    etag: str | None = Field(default=None, max_length=256)


class RateLimitState(_Strict):
    limit: int | None = None
    remaining: int | None = None
    reset_at: datetime | None = None
    retry_after_seconds: float | None = None
    resource: str | None = Field(default=None, max_length=64)


class ConnectorRequest(_Strict):
    stream_name: str = Field(min_length=1, max_length=64)
    page_size: int = Field(default=30, ge=1, le=100)
    checkpoint: ConnectorCheckpointCursor | None = None
    overlap_seconds: int = Field(default=60, ge=0, le=86_400)
    maximum_pages: int | None = Field(default=None, ge=1, le=100)


class NormalizedConnectorEvent(_Strict):
    normalized_event_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=64)
    data_source_id: str = Field(min_length=1, max_length=64)
    connector_type: DataSourceType
    stream_name: str = Field(min_length=1, max_length=64)
    source_record_id: str = Field(min_length=1, max_length=256)
    source_record_version: str | None = Field(default=None, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    subject_type: str = Field(min_length=1, max_length=64)
    subject_external_id: str = Field(min_length=1, max_length=256)
    event_time: datetime
    observed_at: datetime
    normalized_at: datetime
    schema_version: str = "1"
    processing_version: str = "1"
    permission_classification: PermissionClassification = PermissionClassification.PUBLIC
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = Field(min_length=64, max_length=64)
    checkpoint_position: str | None = Field(default=None, max_length=512)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class ConnectorPage:
    stream_name: str
    records: list[dict[str, Any]] = field(default_factory=list)
    normalized_events: list[NormalizedConnectorEvent] = field(default_factory=list)
    next_checkpoint: ConnectorCheckpointCursor | None = None
    rate_limit: RateLimitState | None = None
    has_more: bool = False
    request_count: int = 1
    etag: str | None = None


@runtime_checkable
class Connector(Protocol):
    """Provider connector protocol — HTTP, normalize, and page fetch only."""

    def descriptor(self) -> ConnectorDescriptor: ...

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]: ...

    def list_streams(self, config: dict[str, Any]) -> list[ConnectorStream]: ...

    def fetch_page(
        self,
        context: ConnectorContext,
        config: dict[str, Any],
        request: ConnectorRequest,
    ) -> ConnectorPage: ...
