"""Domain models for observability & AI quality (Phase 3 Prompt 8).

Pydantic records returned by repositories/services and serialized by the API.
These carry only safe, bounded fields — no raw prompts, evidence packages,
tokens or high-cardinality identifiers.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "1"


class SloStatus(str, Enum):
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    BREACHED = "breached"
    INSUFFICIENT_DATA = "insufficient_data"


class AlertState(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class EvaluationStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    INSUFFICIENT_DATA = "insufficient_data"


class ResultStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_DATA = "insufficient_data"


class EvaluationCategory(str, Enum):
    EVIDENCE_COMPLETENESS = "evidence_completeness"
    CITATION_CORRECTNESS = "citation_correctness"
    UNSUPPORTED_CLAIM_RATE = "unsupported_claim_rate"
    DECISION_CONSISTENCY = "decision_consistency"
    FALLBACK_DETERMINISM = "fallback_determinism"
    PROMPT_REGRESSION = "prompt_regression"
    ADVERSARIAL_EVIDENCE = "adversarial_evidence"
    PROVIDER_VARIATION = "provider_variation"


class PredictionQualityStatus(str, Enum):
    AVAILABLE = "available"
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"


class _Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MetricRollupRecord(_Record):
    id: str
    tenant_id: str
    metric_name: str
    window_start: datetime
    window_end: datetime
    value: float
    unit: str
    sample_count: int
    dimensions: dict[str, Any]
    schema_version: str
    service_version: str
    canonical_hash: str
    created_at: datetime


class SloDefinitionRecord(_Record):
    id: str
    tenant_id: str
    slo_key: str
    version: int
    indicator: str
    objective: float
    comparison: str
    unit: str
    window_seconds: int
    min_sample_count: int
    description: str
    schema_version: str
    created_at: datetime


class SloEvaluationRecord(_Record):
    id: str
    tenant_id: str
    slo_key: str
    slo_version: int
    indicator: str
    window_start: datetime
    window_end: datetime
    evaluation_cutoff: datetime
    observed_value: float | None
    objective: float
    sample_count: int
    status: str
    schema_version: str
    canonical_hash: str
    created_at: datetime


class AlertEventRecord(_Record):
    id: str
    tenant_id: str
    fingerprint: str
    severity: str
    state: str
    source: str
    title: str
    reason_code: str
    correlated_slo_key: str | None
    correlated_run_id: str | None
    opened_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    transitions: list[dict[str, Any]]
    schema_version: str


class EvaluationDatasetRecord(_Record):
    id: str
    tenant_id: str
    dataset_key: str
    version: int
    name: str
    description: str
    data_cutoff: datetime | None
    prompt_version: str | None
    published: bool
    case_count: int
    schema_version: str
    canonical_hash: str
    created_at: datetime


class EvaluationRunRecord(_Record):
    id: str
    tenant_id: str
    dataset_id: str
    dataset_version: int
    run_key: str
    provider_variant: str
    prompt_version: str
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    aggregate_score: float | None
    release_gate_passed: bool | None
    critical_violations: int
    started_at: datetime
    completed_at: datetime | None
    schema_version: str
    canonical_hash: str
    created_at: datetime


class EvaluationResultRecord(_Record):
    id: str
    tenant_id: str
    run_id: str
    case_key: str
    category: str
    metric: str
    value: float | None
    threshold: float | None
    status: str
    severity: str
    passed: bool
    detail: dict[str, Any]
    canonical_hash: str
    created_at: datetime


class PredictionQualitySnapshotRecord(_Record):
    id: str
    tenant_id: str
    model_version: str | None
    snapshot_type: str
    window_start: datetime
    window_end: datetime
    data_cutoff: datetime | None
    brier_score: float | None
    calibration_error: float | None
    drift_score: float | None
    drift_method: str | None
    label_coverage: float | None
    sample_count: int
    status: str
    distributions: dict[str, Any]
    schema_version: str
    canonical_hash: str
    created_at: datetime
