"""Domain-facing persistence DTOs — no ORM imports."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import AuditAggregateType, AuditEventType, HumanReviewState
from app.schemas.api_v2 import ReadinessAssessResponse, SimulationResponse

SNAPSHOT_SCHEMA_VERSION = "1"


class AssessmentRecord(BaseModel):
    assessment_record_id: UUID
    assessment_id: str
    project_id: str
    policy_version: str
    schema_version: str
    input_snapshot: dict
    input_snapshot_hash: str
    result_snapshot: dict
    result_snapshot_hash: str
    readiness_score: int
    confidence_score: int
    confidence_level: str
    created_at: datetime
    actor_reference: str | None = None


class AssessmentListItem(BaseModel):
    assessment_record_id: UUID
    assessment_id: str
    project_id: str
    readiness_score: int
    confidence_score: int
    confidence_level: str
    policy_version: str
    created_at: datetime
    latest_review_state: HumanReviewState | None = None


class SimulationRecord(BaseModel):
    simulation_record_id: UUID
    simulation_id: str
    project_id: str
    operation_type: str
    policy_version: str
    schema_version: str
    input_snapshot: dict
    input_snapshot_hash: str
    baseline_snapshot: dict
    baseline_snapshot_hash: str
    proposed_snapshot: dict
    proposed_snapshot_hash: str
    result_snapshot: dict
    result_snapshot_hash: str
    readiness_delta: int
    confidence_delta: int
    created_at: datetime
    actor_reference: str | None = None


class SimulationListItem(BaseModel):
    simulation_record_id: UUID
    simulation_id: str
    project_id: str
    operation_type: str
    readiness_delta: int
    confidence_delta: int
    policy_version: str
    created_at: datetime


class HumanReviewRecord(BaseModel):
    review_id: UUID
    assessment_record_id: UUID
    state: HumanReviewState
    override_reason: str | None = None
    comment: str | None = None
    reviewer_reference: str | None = None
    created_at: datetime
    schema_version: str = SNAPSHOT_SCHEMA_VERSION


class AuditEventRecord(BaseModel):
    audit_event_id: UUID
    event_type: AuditEventType
    aggregate_type: AuditAggregateType
    aggregate_record_id: UUID
    actor_reference: str | None = None
    event_version: str
    metadata: dict = Field(default_factory=dict)
    payload_hash: str | None = None
    occurred_at: datetime


class AssessmentRecordResponse(BaseModel):
    assessment_record_id: UUID
    assessment_id: str
    project_id: str
    policy_version: str
    schema_version: str
    created_at: datetime
    input_snapshot_hash: str
    result_snapshot_hash: str
    result: ReadinessAssessResponse
    latest_review_state: HumanReviewState | None = None
    reviews: list[HumanReviewRecord] = Field(default_factory=list)


class SimulationRecordResponse(BaseModel):
    simulation_record_id: UUID
    simulation_id: str
    project_id: str
    operation_type: str
    policy_version: str
    schema_version: str
    created_at: datetime
    input_snapshot_hash: str
    baseline_snapshot_hash: str
    proposed_snapshot_hash: str
    result_snapshot_hash: str
    result: SimulationResponse


class PaginatedAssessmentList(BaseModel):
    items: list[AssessmentListItem]
    total: int
    limit: int
    offset: int


class PaginatedSimulationList(BaseModel):
    items: list[SimulationListItem]
    total: int
    limit: int
    offset: int
