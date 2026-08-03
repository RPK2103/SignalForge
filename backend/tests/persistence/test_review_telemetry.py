"""Phase-2 assessment human-review telemetry (Prompt 8 completeness)."""

from __future__ import annotations

import pytest

from app.domain.enums import HumanReviewState
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider
from app.schemas.api_v2 import ReadinessAssessRequest
from app.security.context import internal_system_context
from app.security.enums import Permission, SecurityRole
from app.security.exceptions import AuthorizationError
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService
from app.services.persistence.review_persistence_service import (
    HumanReviewPersistenceService,
    HumanReviewRequest,
)


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


def _reviewer_ctx():
    return internal_system_context(
        "novabank",
        correlation_id="review-telemetry",
        roles=frozenset({SecurityRole.TENANT_ADMIN}),
    )


def _denied_ctx():
    return internal_system_context(
        "novabank",
        correlation_id="review-denied",
        roles=frozenset({SecurityRole.EXECUTIVE_READER}),
        permissions=frozenset({Permission.CHIEF_OF_STAFF_READ}),
    )


def test_assessment_human_review_emits_cos_review(unit_of_work, obs_provider):
    ctx = _reviewer_ctx()
    assessments = AssessmentPersistenceService(unit_of_work)
    reviews = HumanReviewPersistenceService(unit_of_work)
    created = assessments.create_assessment(
        ctx,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi", "vikram"],
        ),
    )
    obs_provider.reset()
    reviews.add_review(
        ctx,
        created.assessment_record_id,
        HumanReviewRequest(state=HumanReviewState.ACCEPTED, reviewer_reference="r1"),
    )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="accepted") == 1

    reviews.add_review(
        ctx,
        created.assessment_record_id,
        HumanReviewRequest(
            state=HumanReviewState.OVERRIDDEN,
            reviewer_reference="r2",
            override_reason="adjusted judgment",
        ),
    )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="corrected") == 1
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 2


def test_assessment_review_auth_denial_not_counted(unit_of_work, obs_provider):
    admin = _reviewer_ctx()
    assessments = AssessmentPersistenceService(unit_of_work)
    created = assessments.create_assessment(
        admin,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi"],
        ),
    )
    obs_provider.reset()
    with pytest.raises(AuthorizationError):
        HumanReviewPersistenceService(unit_of_work).add_review(
            _denied_ctx(),
            created.assessment_record_id,
            HumanReviewRequest(state=HumanReviewState.ACCEPTED),
        )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0


def test_assessment_needs_more_data_outcome(unit_of_work, obs_provider):
    ctx = _reviewer_ctx()
    assessments = AssessmentPersistenceService(unit_of_work)
    created = assessments.create_assessment(
        ctx,
        ReadinessAssessRequest(
            project_id="azure_ai_migration",
            engineer_ids=["kavi"],
        ),
    )
    obs_provider.reset()
    HumanReviewPersistenceService(unit_of_work).add_review(
        ctx,
        created.assessment_record_id,
        HumanReviewRequest(
            state=HumanReviewState.NEEDS_MORE_DATA,
            comment="Need more evidence",
        ),
    )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="needs_follow_up") == 1
