"""Leadership Brief persistence application service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.db.types import new_uuid
from app.db.unit_of_work import UnitOfWork
from app.domain.enums import AuditAggregateType, AuditEventType
from app.domain.leadership_brief_models import (
    LeadershipBrief,
    LeadershipBriefRecord,
    LeadershipBriefResponse,
)
from app.domain.persistence_models import SNAPSHOT_SCHEMA_VERSION, AuditEventRecord
from app.schemas.api_v2 import ReadinessAssessResponse
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.enums import Permission
from app.services.leadership_brief.evidence_package import (
    build_evidence_package,
    evidence_package_to_canonical_dict,
)
from app.services.leadership_brief.orchestrator import LeadershipBriefOrchestrator
from app.services.persistence.exceptions import LeadershipBriefGenerationFailed
from app.services.persistence.snapshot_service import (
    build_snapshot_payload,
    snapshot_hash,
    verify_snapshot_hash,
)


class LeadershipBriefPersistenceService:
    def __init__(
        self,
        uow: UnitOfWork,
        orchestrator: LeadershipBriefOrchestrator | None = None,
    ) -> None:
        self._uow = uow
        self._orchestrator = orchestrator or LeadershipBriefOrchestrator()
        self._authz = AuthorizationService()

    def generate_leadership_brief(
        self,
        context: SecurityContext,
        assessment_record_id: UUID,
        *,
        actor_reference: str | None = None,
    ) -> LeadershipBriefResponse:
        # Service-layer authorization (deny-by-default): generating an executive
        # leadership brief requires ``chief_of_staff.generate``.
        self._authz.require_context(context, Permission.CHIEF_OF_STAFF_GENERATE)
        record = self._uow.assessments.get_by_record_id(assessment_record_id)
        verify_snapshot_hash(record.input_snapshot, record.input_snapshot_hash)
        verify_snapshot_hash(record.result_snapshot, record.result_snapshot_hash)
        result = ReadinessAssessResponse.model_validate(record.result_snapshot["data"])
        latest_review = self._uow.reviews.get_latest_for_assessment(assessment_record_id)
        latest_review_state = latest_review.state.value if latest_review else None

        package = build_evidence_package(
            assessment_record_id=assessment_record_id,
            result=result,
            latest_review_state=latest_review_state,
        )
        evidence_snapshot = build_snapshot_payload(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            policy_version=result.policy_version,
            data=evidence_package_to_canonical_dict(package),
        )
        package_hash = snapshot_hash(evidence_snapshot)
        verify_snapshot_hash(evidence_snapshot, package_hash)

        try:
            outcome = self._orchestrator.generate(package)
        except Exception as exc:
            raise LeadershipBriefGenerationFailed(
                "Leadership Brief generation failed unexpectedly"
            ) from exc

        output_snapshot = build_snapshot_payload(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            policy_version=result.policy_version,
            data=outcome.brief.model_dump(mode="json"),
        )
        output_hash = snapshot_hash(output_snapshot)
        record_id = new_uuid()
        created_at = datetime.now(timezone.utc)

        brief_record = LeadershipBriefRecord(
            leadership_brief_record_id=record_id,
            assessment_record_id=assessment_record_id,
            assessment_id=record.assessment_id,
            prompt_version=outcome.prompt_version,
            provider_mode=outcome.provider_mode,
            generation_status=outcome.generation_status,
            failure_category=outcome.failure_category,
            evidence_package_snapshot=evidence_snapshot,
            evidence_package_hash=package_hash,
            output_snapshot=output_snapshot,
            output_snapshot_hash=output_hash,
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            created_at=created_at,
        )

        def _persist(uow: UnitOfWork) -> LeadershipBriefResponse:
            uow.leadership_briefs.add(brief_record)
            uow.audit_events.append(
                AuditEventRecord(
                    audit_event_id=uuid4(),
                    event_type=AuditEventType.LEADERSHIP_BRIEF_CREATED,
                    aggregate_type=AuditAggregateType.ASSESSMENT,
                    aggregate_record_id=assessment_record_id,
                    actor_reference=actor_reference,
                    event_version="1",
                    metadata={
                        "leadership_brief_record_id": str(record_id),
                        "assessment_record_id": str(assessment_record_id),
                        "assessment_id": record.assessment_id,
                        "prompt_version": outcome.prompt_version,
                        "provider_mode": outcome.provider_mode.value,
                        "generation_status": outcome.generation_status.value,
                        "failure_category": (
                            outcome.failure_category.value if outcome.failure_category else None
                        ),
                        "evidence_package_hash": package_hash,
                        "output_snapshot_hash": output_hash,
                    },
                    payload_hash=output_hash,
                    occurred_at=created_at,
                )
            )
            return self._to_response(brief_record, outcome.brief)

        return self._uow.execute(_persist)

    def list_leadership_briefs(
        self,
        assessment_record_id: UUID,
    ) -> list[LeadershipBriefResponse]:
        self._uow.assessments.get_by_record_id(assessment_record_id)
        records = self._uow.leadership_briefs.list_for_assessment(assessment_record_id)
        responses: list[LeadershipBriefResponse] = []
        for item in records:
            verify_snapshot_hash(item.evidence_package_snapshot, item.evidence_package_hash)
            verify_snapshot_hash(item.output_snapshot, item.output_snapshot_hash)
            brief = LeadershipBrief.model_validate(item.output_snapshot["data"])
            responses.append(self._to_response(item, brief))
        return responses

    @staticmethod
    def _to_response(
        record: LeadershipBriefRecord,
        brief: LeadershipBrief,
    ) -> LeadershipBriefResponse:
        return LeadershipBriefResponse(
            leadership_brief_record_id=record.leadership_brief_record_id,
            assessment_record_id=record.assessment_record_id,
            assessment_id=record.assessment_id,
            evidence_package_hash=record.evidence_package_hash,
            output_snapshot_hash=record.output_snapshot_hash,
            failure_category=record.failure_category,
            created_at=record.created_at,
            brief=brief,
        )
