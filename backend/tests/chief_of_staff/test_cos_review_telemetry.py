"""Chief-of-Staff human-review telemetry integration (Prompt 8 completeness).

Drives ``ChiefOfStaffService.append_review`` and asserts bounded ``cos.reviews``
samples flush only after a durable UoW commit. Phase-2 assessment reviews are
covered in ``tests/persistence/test_review_telemetry.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffReviewState,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import ChiefOfStaffRequest
from app.observability.attributes import ALLOWED_ATTRIBUTES
from app.observability.domain import record_cos_review
from app.observability.metrics import MetricName
from app.observability.metrics_reader import MetricsReader
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import (
    get_observability_provider,
    reset_observability_provider,
    set_observability_provider,
)
from app.security.context import internal_system_context
from app.security.enums import Permission, SecurityRole
from app.security.exceptions import AuthorizationError
from app.services.chief_of_staff.service import ChiefOfStaffService
from app.services.enterprise.exceptions import EnterpriseNotFoundError

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


def _reviewer_ctx(tenant: str = "novabank"):
    return internal_system_context(
        tenant,
        correlation_id="review-telemetry",
        roles=frozenset({SecurityRole.TENANT_ADMIN}),
    )


def _denied_ctx(tenant: str = "novabank"):
    return internal_system_context(
        tenant,
        correlation_id="review-denied",
        roles=frozenset({SecurityRole.EXECUTIVE_READER}),
        permissions=frozenset({Permission.CHIEF_OF_STAFF_READ}),
    )


def _first_project_id(uow, ctx) -> str:
    projects = uow.initiatives_projects.list_projects(ctx, limit=5, offset=0)
    assert projects.items
    return projects.items[0].enterprise_project_id


def _generate_brief(uow, ctx):
    service = ChiefOfStaffService(uow)
    outcome = service.generate(
        ctx,
        ChiefOfStaffRequest(
            tenant_id=ctx.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=_first_project_id(uow, ctx),
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    return outcome.brief.brief_id


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (ChiefOfStaffReviewState.ACCEPTED, "accepted"),
        (ChiefOfStaffReviewState.NEEDS_REVISION, "corrected"),
        (ChiefOfStaffReviewState.REJECTED, "rejected"),
        (ChiefOfStaffReviewState.NEEDS_MORE_EVIDENCE, "needs_follow_up"),
    ],
)
def test_cos_review_committed_outcomes(
    seeded_novabank, uow, novabank_tenant, obs_provider, state, expected
):
    brief_id = _generate_brief(uow, novabank_tenant)
    obs_provider.reset()
    security = _reviewer_ctx()
    ChiefOfStaffService(uow).append_review(
        novabank_tenant,
        brief_id=brief_id,
        review_state=state,
        notes="should never appear in metrics",
        security=security,
    )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome=expected) == 1
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 1


def test_cos_review_rollback_discards_success_when_commit_fails(
    seeded_novabank, uow, novabank_tenant, obs_provider, monkeypatch
):
    brief_id = _generate_brief(uow, novabank_tenant)
    obs_provider.reset()

    # Queue pending success then fail the durable commit (mirrors UoW pending path).
    uow.cos_reviews.append(
        novabank_tenant,
        brief_id=brief_id,
        review_state=ChiefOfStaffReviewState.ACCEPTED,
        reviewer_context="test",
        notes="secret note",
    )
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0

    def _boom():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(uow.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit failed"):
        uow.commit()
    uow.rollback()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0


def test_cos_review_authorization_denial_not_counted(
    seeded_novabank, uow, novabank_tenant, obs_provider
):
    brief_id = _generate_brief(uow, novabank_tenant)
    obs_provider.reset()
    with pytest.raises(AuthorizationError):
        ChiefOfStaffService(uow).append_review(
            novabank_tenant,
            brief_id=brief_id,
            review_state=ChiefOfStaffReviewState.ACCEPTED,
            security=_denied_ctx(),
        )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0


def test_cos_review_missing_security_fails_closed(
    seeded_novabank, uow, novabank_tenant, obs_provider
):
    """Direct call with security=None must deny — no optional bypass."""
    brief_id = _generate_brief(uow, novabank_tenant)
    obs_provider.reset()
    with pytest.raises(AuthorizationError) as exc_info:
        ChiefOfStaffService(uow).append_review(
            novabank_tenant,
            brief_id=brief_id,
            review_state=ChiefOfStaffReviewState.ACCEPTED,
            security=None,  # type: ignore[arg-type]
        )
    assert exc_info.value.reason_code == "no_security_context"
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0


def test_cos_review_empty_roles_fails_closed(seeded_novabank, uow, novabank_tenant, obs_provider):
    brief_id = _generate_brief(uow, novabank_tenant)
    obs_provider.reset()
    empty = internal_system_context(
        "novabank",
        correlation_id="review-empty-roles",
        roles=frozenset(),
        permissions=frozenset(),
    )
    with pytest.raises(AuthorizationError):
        ChiefOfStaffService(uow).append_review(
            novabank_tenant,
            brief_id=brief_id,
            review_state=ChiefOfStaffReviewState.ACCEPTED,
            security=empty,
        )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0


def test_cos_review_wrong_tenant_not_counted(seeded_novabank, uow, novabank_tenant, obs_provider):
    brief_id = _generate_brief(uow, novabank_tenant)
    obs_provider.reset()
    foreign = _reviewer_ctx("othercorp")
    with pytest.raises(AuthorizationError):
        ChiefOfStaffService(uow).append_review(
            novabank_tenant,
            brief_id=brief_id,
            review_state=ChiefOfStaffReviewState.ACCEPTED,
            security=foreign,
        )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0


def test_cos_review_missing_brief_emits_error_not_success(
    seeded_novabank, uow, novabank_tenant, obs_provider
):
    obs_provider.reset()
    with pytest.raises(EnterpriseNotFoundError):
        ChiefOfStaffService(uow).append_review(
            novabank_tenant,
            brief_id="brief-does-not-exist",
            review_state=ChiefOfStaffReviewState.ACCEPTED,
            security=_reviewer_ctx(),
        )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="error") == 1
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="accepted") == 0


def test_cos_review_telemetry_provider_failure_keeps_review(seeded_novabank, uow, novabank_tenant):
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("boom")

    brief_id = _generate_brief(uow, novabank_tenant)
    set_observability_provider(ExplodingProvider())
    try:
        review = ChiefOfStaffService(uow).append_review(
            novabank_tenant,
            brief_id=brief_id,
            review_state=ChiefOfStaffReviewState.ACCEPTED,
            security=_reviewer_ctx(),
        )
        assert review.review_state == ChiefOfStaffReviewState.ACCEPTED
    finally:
        reset_observability_provider()


def test_cos_review_attributes_are_bounded(seeded_novabank, uow, novabank_tenant, obs_provider):
    brief_id = _generate_brief(uow, novabank_tenant)
    obs_provider.reset()
    ChiefOfStaffService(uow).append_review(
        novabank_tenant,
        brief_id=brief_id,
        review_state=ChiefOfStaffReviewState.REJECTED,
        notes="alice@example.com leaked note with uuid 550e8400-e29b-41d4-a716-446655440000",
        security=_reviewer_ctx(),
    )
    for _name, attrs in obs_provider.counters:
        keys = set(dict(attrs))
        assert keys <= ALLOWED_ATTRIBUTES
        for value in dict(attrs).values():
            assert "@" not in value
            assert "550e8400" not in value
            assert "leaked" not in value


def test_review_metric_reaches_reader(seeded_novabank, uow, novabank_tenant, obs_provider):
    brief_id = _generate_brief(uow, novabank_tenant)
    obs_provider.reset()
    ChiefOfStaffService(uow).append_review(
        novabank_tenant,
        brief_id=brief_id,
        review_state=ChiefOfStaffReviewState.ACCEPTED,
        security=_reviewer_ctx(),
    )
    reader = MetricsReader(get_observability_provider())
    indicator = reader.cos_review_total(outcome="accepted")
    assert indicator.sample_count == 1
    assert indicator.value == 1.0
    assert reader.cos_review_total().sample_count == 1


def test_cos_review_each_committed_row_counts_once(
    seeded_novabank, uow, novabank_tenant, obs_provider
):
    """Repeated reviews count once per newly committed review row — never double-count."""
    brief_id = _generate_brief(uow, novabank_tenant)
    obs_provider.reset()
    service = ChiefOfStaffService(uow)
    security = _reviewer_ctx()
    service.append_review(
        novabank_tenant,
        brief_id=brief_id,
        review_state=ChiefOfStaffReviewState.ACCEPTED,
        security=security,
    )
    service.append_review(
        novabank_tenant,
        brief_id=brief_id,
        review_state=ChiefOfStaffReviewState.NEEDS_REVISION,
        security=security,
    )
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="accepted") == 1
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="corrected") == 1
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 2
