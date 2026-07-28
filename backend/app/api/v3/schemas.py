"""Request/response contracts for the v3 enterprise API.

All responses reuse the strictly-typed domain DTOs in
``app.domain.enterprise_models`` (no ORM leakage). Request models add bounded
validation and OpenAPI examples.
"""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import (
    DataSourceType,
    EnterpriseEntityType,
    EvidenceSignalType,
    IngestionErrorCategory,
    IngestionRunStatus,
    IngestionRunType,
    PermissionClassification,
)

# Bounded evidence payload size (canonical JSON characters) to prevent abuse.
MAX_EVIDENCE_PAYLOAD_CHARS = 16_384


class RegisterDataSourceRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "source_type": "github",
                "display_name": "NovaBank GitHub Org",
                "credential_reference": "env://SIGNALFORGE_GITHUB_TOKEN",
                "permission_classification": "internal",
                "connector_config": {
                    "owner": "octocat",
                    "repository": "Hello-World",
                    "enabled_streams": ["repository", "issues"],
                    "page_size": 30,
                    "maximum_pages": 2,
                },
            }
        },
    )

    source_type: DataSourceType
    display_name: str = Field(min_length=1, max_length=128)
    credential_reference: str | None = Field(default=None, max_length=256)
    config_reference: str | None = Field(default=None, max_length=256)
    connector_config: dict | None = None
    permission_classification: PermissionClassification = PermissionClassification.INTERNAL


class StartIngestionRunRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"data_source_id": "ds_abc123", "run_type": "incremental"}},
    )

    data_source_id: str = Field(min_length=1, max_length=64)
    run_type: IngestionRunType = IngestionRunType.INCREMENTAL
    run_key: str | None = Field(default=None, max_length=128)


class CompleteIngestionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IngestionRunStatus
    records_read: int = Field(default=0, ge=0)
    records_written: int = Field(default=0, ge=0)
    records_skipped: int = Field(default=0, ge=0)
    error_category: IngestionErrorCategory = IngestionErrorCategory.NONE
    error_summary: str | None = Field(default=None, max_length=1024)


class AppendEvidenceRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "data_source_id": "ds_abc123",
                "source_record_id": "github-rec-1",
                "signal_type": "commit",
                "subject_type": "repository",
                "subject_id": "repo_abc123",
                "event_time": "2026-01-06T09:00:00Z",
                "payload": {"kind": "commit", "sha": "deadbeef"},
            }
        },
    )

    data_source_id: str = Field(min_length=1, max_length=64)
    source_record_id: str = Field(min_length=1, max_length=256)
    signal_type: EvidenceSignalType
    subject_type: EnterpriseEntityType
    subject_id: str = Field(min_length=1, max_length=128)
    event_time: datetime
    observed_at: datetime | None = None
    ingestion_run_id: str | None = Field(default=None, max_length=64)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    permission_classification: PermissionClassification = PermissionClassification.INTERNAL
    payload: dict = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _bound_payload(cls, value: dict) -> dict:
        if len(json.dumps(value, default=str)) > MAX_EVIDENCE_PAYLOAD_CHARS:
            raise ValueError(f"Evidence payload exceeds {MAX_EVIDENCE_PAYLOAD_CHARS} characters")
        return value


class EvidenceAppendResponse(BaseModel):
    created: bool
    signal: dm.EvidenceSignal


class DemoTenantSummary(BaseModel):
    tenant_id: str
    organization_id: str | None
    counts: dict[str, int]
