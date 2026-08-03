"""Human review persistence application service."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, model_validator

from app.db.unit_of_work import UnitOfWork
from app.domain.enums import AuditAggregateType, AuditEventType, HumanReviewState
from app.domain.persistence_models import (
    SNAPSHOT_SCHEMA_VERSION,
    AssessmentRecordResponse,
    AuditEventRecord,
    HumanReviewRecord,
)
from app.observability.domain import record_cos_review
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.enums import Permission
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService
from app.services.persistence.exceptions import RecordNotFoundError

# Map Phase-2 assessment review states onto the bounded cos.reviews vocabulary.
_HUMAN_REVIEW_OUTCOME: dict[HumanReviewState, str] = {
    HumanReviewState.ACCEPTED: "accepted",
    HumanReviewState.OVERRIDDEN: "corrected",
    HumanReviewState.NEEDS_MORE_DATA: "needs_follow_up",
}


class HumanReviewRequest(BaseModel):
    state: HumanReviewState
    reviewer_reference: str | None = None
    comment: str | None = None
    override_reason: str | None = None

    @model_validator(mode="after")
    def validate_state_rules(self):
        if self.state == HumanReviewState.OVERRIDDEN:
            if not self.override_reason or not self.override_reason.strip():
                raise ValueError("override_reason is required when state is overridden")
        if self.state == HumanReviewState.NEEDS_MORE_DATA:
            if not self.comment or not self.comment.strip():
                raise ValueError("comment is required when state is needs_more_data")
        return self


class HumanReviewPersistenceService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._assessments = AssessmentPersistenceService(uow)
        self._authz = AuthorizationService()

    def add_review(
        self,
        context: SecurityContext,
        assessment_record_id: UUID,
        request: HumanReviewRequest,
    ) -> AssessmentRecordResponse:
        # Service-layer authorization (deny-by-default): appending a human review
        # of a leadership brief requires ``chief_of_staff.review``.
        self._authz.require_context(context, Permission.CHIEF_OF_STAFF_REVIEW)
        try:
            self._uow.assessments.get_by_record_id(assessment_record_id)
        except RecordNotFoundError:
            raise

        review_id = uuid4()
        created_at = datetime.now(timezone.utc)
        review = HumanReviewRecord(
            review_id=review_id,
            assessment_record_id=assessment_record_id,
            state=request.state,
            override_reason=request.override_reason,
            comment=request.comment,
            reviewer_reference=request.reviewer_reference,
            created_at=created_at,
            schema_version=SNAPSHOT_SCHEMA_VERSION,
        )
        outcome = _HUMAN_REVIEW_OUTCOME.get(request.state, "error")

        def _persist(uow: UnitOfWork) -> None:
            uow.reviews.add(review)
            uow.audit_events.append(
                AuditEventRecord(
                    audit_event_id=uuid4(),
                    event_type=AuditEventType.HUMAN_REVIEW_CREATED,
                    aggregate_type=AuditAggregateType.HUMAN_REVIEW,
                    aggregate_record_id=review_id,
                    actor_reference=request.reviewer_reference,
                    event_version="1",
                    metadata={
                        "assessment_record_id": str(assessment_record_id),
                        "state": request.state.value,
                    },
                    payload_hash=None,
                    occurred_at=created_at,
                )
            )
            # Bounded outcome only — never review text, reviewer identity, or IDs.
            uow.note_pending_telemetry(lambda o=outcome: record_cos_review(outcome=o))

        try:
            self._uow.execute(_persist)
        except Exception:
            record_cos_review(outcome="error")
            raise
        return self._assessments.get_assessment(assessment_record_id)
