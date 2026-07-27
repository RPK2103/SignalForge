"""Compute-and-persist assessment application service."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.db.types import new_uuid
from app.db.unit_of_work import UnitOfWork
from app.domain.enums import AuditAggregateType, AuditEventType
from app.domain.persistence_models import (
    SNAPSHOT_SCHEMA_VERSION,
    AssessmentRecord,
    AssessmentRecordResponse,
    AuditEventRecord,
    PaginatedAssessmentList,
)
from app.schemas.api_v2 import ReadinessAssessRequest, ReadinessAssessResponse
from app.services.persistence.snapshot_service import (
    build_assessment_input_snapshot,
    build_assessment_result_snapshot,
    snapshot_hash,
    verify_snapshot_hash,
)
from app.services.readiness_orchestrator import ReadinessOrchestrator


class AssessmentPersistenceService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._orchestrator = ReadinessOrchestrator(catalog=uow.catalog)

    def create_assessment(
        self,
        request: ReadinessAssessRequest,
        *,
        actor_reference: str | None = None,
    ) -> AssessmentRecordResponse:
        result = self._orchestrator.assess(request)
        policy_version = result.policy_version
        input_snapshot = build_assessment_input_snapshot(
            project_id=request.project_id,
            engineer_ids=request.engineer_ids,
            policy_version=policy_version,
        )
        result_snapshot = build_assessment_result_snapshot(result, policy_version=policy_version)
        input_hash = snapshot_hash(input_snapshot)
        result_hash = snapshot_hash(result_snapshot)
        record_id = new_uuid()
        created_at = datetime.now(timezone.utc)

        record = AssessmentRecord(
            assessment_record_id=record_id,
            assessment_id=result.assessment_id,
            project_id=result.project_id,
            policy_version=policy_version,
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            input_snapshot=input_snapshot,
            input_snapshot_hash=input_hash,
            result_snapshot=result_snapshot,
            result_snapshot_hash=result_hash,
            readiness_score=result.readiness_score,
            confidence_score=result.confidence_score,
            confidence_level=result.confidence_level.value,
            created_at=created_at,
            actor_reference=actor_reference,
        )

        def _persist(uow: UnitOfWork) -> AssessmentRecordResponse:
            uow.assessments.add(record)
            uow.assessments.add_risk_projections(
                record_id,
                [finding.model_dump(mode="json") for finding in result.risk_findings],
            )
            uow.assessments.add_trace_projections(
                record_id,
                [trace.model_dump(mode="json") for trace in result.decision_trace],
            )
            uow.audit_events.append(
                AuditEventRecord(
                    audit_event_id=uuid4(),
                    event_type=AuditEventType.ASSESSMENT_CREATED,
                    aggregate_type=AuditAggregateType.ASSESSMENT,
                    aggregate_record_id=record_id,
                    actor_reference=actor_reference,
                    event_version="1",
                    metadata={
                        "assessment_id": result.assessment_id,
                        "project_id": result.project_id,
                        "policy_version": policy_version,
                        "result_snapshot_hash": result_hash,
                    },
                    payload_hash=result_hash,
                    occurred_at=created_at,
                )
            )
            return AssessmentRecordResponse(
                assessment_record_id=record_id,
                assessment_id=result.assessment_id,
                project_id=result.project_id,
                policy_version=policy_version,
                schema_version=SNAPSHOT_SCHEMA_VERSION,
                created_at=created_at,
                input_snapshot_hash=input_hash,
                result_snapshot_hash=result_hash,
                result=result,
                latest_review_state=None,
                reviews=[],
            )

        return self._uow.execute(_persist)

    def get_assessment(self, record_id: UUID) -> AssessmentRecordResponse:
        record = self._uow.assessments.get_by_record_id(record_id)
        verify_snapshot_hash(record.input_snapshot, record.input_snapshot_hash)
        verify_snapshot_hash(record.result_snapshot, record.result_snapshot_hash)
        result = ReadinessAssessResponse.model_validate(record.result_snapshot["data"])
        reviews = self._uow.reviews.list_for_assessment(record_id)
        latest = self._uow.reviews.get_latest_for_assessment(record_id)
        return AssessmentRecordResponse(
            assessment_record_id=record.assessment_record_id,
            assessment_id=record.assessment_id,
            project_id=record.project_id,
            policy_version=record.policy_version,
            schema_version=record.schema_version,
            created_at=record.created_at,
            input_snapshot_hash=record.input_snapshot_hash,
            result_snapshot_hash=record.result_snapshot_hash,
            result=result,
            latest_review_state=latest.state if latest else None,
            reviews=reviews,
        )

    def list_assessments(
        self,
        *,
        project_id: str | None = None,
        assessment_id: str | None = None,
        review_state=None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedAssessmentList:
        return self._uow.assessments.list(
            project_id=project_id,
            assessment_id=assessment_id,
            review_state=review_state,
            limit=limit,
            offset=offset,
        )
