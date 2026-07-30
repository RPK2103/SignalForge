"""Human review persistence tests."""

import pytest

from app.domain.enums import HumanReviewState
from app.schemas.api_v2 import ReadinessAssessRequest
from app.security.context import internal_system_context
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService
from app.services.persistence.review_persistence_service import (
    HumanReviewPersistenceService,
    HumanReviewRequest,
)

CTX = internal_system_context("novabank", correlation_id="test")


def test_append_reviews(unit_of_work):
    assessments = AssessmentPersistenceService(unit_of_work)
    reviews = HumanReviewPersistenceService(unit_of_work)
    created = assessments.create_assessment(
        CTX,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        ),
    )
    original_hash = created.result_snapshot_hash
    reviews.add_review(
        CTX,
        created.assessment_record_id,
        HumanReviewRequest(state=HumanReviewState.ACCEPTED, reviewer_reference="reviewer-1"),
    )
    updated = reviews.add_review(
        CTX,
        created.assessment_record_id,
        HumanReviewRequest(
            state=HumanReviewState.NEEDS_MORE_DATA,
            reviewer_reference="reviewer-2",
            comment="Need more evidence",
        ),
    )
    assert updated.result_snapshot_hash == original_hash
    assert len(updated.reviews) == 2
    assert updated.latest_review_state == HumanReviewState.NEEDS_MORE_DATA


def test_overridden_requires_reason(unit_of_work):
    assessments = AssessmentPersistenceService(unit_of_work)
    assessments.create_assessment(
        CTX,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        ),
    )
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        HumanReviewRequest(state=HumanReviewState.OVERRIDDEN)
