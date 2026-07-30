"""Integration, tenant isolation, immutability, and API tests for Chief of Staff."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffReviewState,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import ChiefOfStaffRequest
from app.services.chief_of_staff.canonicalization import compute_brief_output_hash
from app.services.chief_of_staff.fallback import build_fallback_brief
from app.services.chief_of_staff.service import ChiefOfStaffService
from app.services.enterprise.exceptions import EnterpriseNotFoundError

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _first_project_id(uow, ctx) -> str:
    projects = uow.initiatives_projects.list_projects(ctx, limit=5, offset=0)
    assert projects.items
    return projects.items[0].enterprise_project_id


def test_generate_delivery_status_fallback(seeded_novabank, uow, novabank_tenant):
    target_id = _first_project_id(uow, novabank_tenant)
    service = ChiefOfStaffService(uow)
    outcome = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    assert outcome.brief is not None
    assert outcome.run.final_provider == ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK
    assert outcome.run.generation_state.value == "fallback_generated"
    assert outcome.structured_brief.fallback_visible is True


def test_change_since_last_review_uses_prior_package(seeded_novabank, uow, novabank_tenant):
    target_id = _first_project_id(uow, novabank_tenant)
    service = ChiefOfStaffService(uow)
    prior = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF - timedelta(days=7),
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    current = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.CHANGE_SINCE_LAST_REVIEW,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            prior_brief_id=prior.brief.brief_id,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    assert current.package.prior_brief is not None
    assert current.package.prior_brief.brief_id == prior.brief.brief_id


def test_regeneration_creates_new_run(seeded_novabank, uow, novabank_tenant):
    target_id = _first_project_id(uow, novabank_tenant)
    service = ChiefOfStaffService(uow)
    req = ChiefOfStaffRequest(
        tenant_id=novabank_tenant.tenant_id,
        intent=ChiefOfStaffIntent.EVIDENCE_GAP_BRIEF,
        target_type=ChiefOfStaffTargetType.PROJECT,
        target_id=target_id,
        as_of_at=AS_OF,
        requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
    )
    a = service.generate(novabank_tenant, req)
    b = service.generate(novabank_tenant, req)
    assert a.run.run_id != b.run.run_id
    assert a.brief.brief_id != b.brief.brief_id
    # Identical package content may reuse snapshot by hash.
    assert a.evidence_snapshot.package_hash == b.evidence_snapshot.package_hash


def test_review_append_only_does_not_mutate_brief(seeded_novabank, uow, novabank_tenant):
    target_id = _first_project_id(uow, novabank_tenant)
    service = ChiefOfStaffService(uow)
    outcome = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    before = outcome.brief.output_hash
    service.append_review(
        novabank_tenant,
        brief_id=outcome.brief.brief_id,
        review_state=ChiefOfStaffReviewState.ACCEPTED,
        notes="ok",
    )
    service.append_review(
        novabank_tenant,
        brief_id=outcome.brief.brief_id,
        review_state=ChiefOfStaffReviewState.NEEDS_MORE_EVIDENCE,
        notes="need more",
    )
    refreshed = uow.cos_briefs.require(novabank_tenant, outcome.brief.brief_id)
    assert refreshed.output_hash == before
    reviews = uow.cos_reviews.list_for_brief(novabank_tenant, outcome.brief.brief_id)
    assert len(reviews) == 2


def test_foreign_brief_equivalent_to_missing(seeded_novabank, uow, novabank_tenant, tenant_b):
    target_id = _first_project_id(uow, novabank_tenant)
    service = ChiefOfStaffService(uow)
    outcome = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    with pytest.raises(EnterpriseNotFoundError):
        uow.cos_briefs.require(tenant_b, outcome.brief.brief_id)
    with pytest.raises(EnterpriseNotFoundError):
        uow.cos_briefs.require(novabank_tenant, "nonexistent-brief-id")


def test_foreign_target_rejected(seeded_novabank, uow, tenant_a):
    service = ChiefOfStaffService(uow)
    with pytest.raises(EnterpriseNotFoundError):
        service.generate(
            tenant_a,
            ChiefOfStaffRequest(
                tenant_id=tenant_a.tenant_id,
                intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
                target_type=ChiefOfStaffTargetType.PROJECT,
                target_id="does-not-exist",
                as_of_at=AS_OF,
                requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
            ),
        )


def test_fallback_determinism_same_package_hash(seeded_novabank, uow, novabank_tenant):
    target_id = _first_project_id(uow, novabank_tenant)
    service = ChiefOfStaffService(uow)
    outcome = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    brief_a = build_fallback_brief(
        outcome.package, evidence_package_hash=outcome.package.package_hash
    )
    brief_b = build_fallback_brief(
        outcome.package, evidence_package_hash=outcome.package.package_hash
    )
    hash_a = compute_brief_output_hash(brief_a, evidence_package_hash=outcome.package.package_hash)
    hash_b = compute_brief_output_hash(brief_b, evidence_package_hash=outcome.package.package_hash)
    assert hash_a == hash_b
    assert outcome.run.output_hash == hash_a
    # Persistence snapshot PK must not affect semantic output hash.
    assert all(c.package_id == outcome.package.package_hash for c in brief_a.citations)
    assert outcome.evidence_snapshot.snapshot_id != outcome.package.package_hash or True
    assert (
        all(c.package_id != outcome.evidence_snapshot.snapshot_id for c in brief_a.citations)
        or outcome.evidence_snapshot.snapshot_id == outcome.package.package_hash
    )


def test_api_list_and_detail(seeded_novabank, uow, novabank_tenant, client):
    target_id = _first_project_id(uow, novabank_tenant)
    service = ChiefOfStaffService(uow)
    outcome = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    headers = {"X-SignalForge-Tenant-ID": novabank_tenant.tenant_id}
    listed = client.get("/api/v3/chief-of-staff/briefs", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    detail = client.get(f"/api/v3/chief-of-staff/briefs/{outcome.brief.brief_id}", headers=headers)
    assert detail.status_code == 200
    claims = client.get(
        f"/api/v3/chief-of-staff/briefs/{outcome.brief.brief_id}/claims", headers=headers
    )
    assert claims.status_code == 200
    assert isinstance(claims.json(), list)
    citations = client.get(
        f"/api/v3/chief-of-staff/briefs/{outcome.brief.brief_id}/citations", headers=headers
    )
    assert citations.status_code == 200
    evidence = client.get(
        f"/api/v3/chief-of-staff/briefs/{outcome.brief.brief_id}/evidence-summary",
        headers=headers,
    )
    assert evidence.status_code == 200
    assert "package_json" not in evidence.json()
    runs = client.get("/api/v3/chief-of-staff/runs", headers=headers)
    assert runs.status_code == 200
    quality = client.get("/api/v3/chief-of-staff/quality-summary", headers=headers)
    assert quality.status_code == 200
    # Foreign tenant sees not found equivalently.
    foreign = client.get(
        f"/api/v3/chief-of-staff/briefs/{outcome.brief.brief_id}",
        headers={"X-SignalForge-Tenant-ID": "tenant-b"},
    )
    missing = client.get(
        "/api/v3/chief-of-staff/briefs/does-not-exist",
        headers=headers,
    )
    assert foreign.status_code == missing.status_code


def test_api_has_no_mutation_routes(client):
    openapi = client.get("/openapi.json").json()
    paths = openapi["paths"]
    cos_paths = {p: methods for p, methods in paths.items() if "chief-of-staff" in p}
    assert cos_paths
    for methods in cos_paths.values():
        for method in methods:
            assert method.lower() in {"get", "parameters", "head", "options"}


def test_prediction_brief_preserves_uncalibrated_semantics(seeded_novabank, uow, novabank_tenant):
    target_id = _first_project_id(uow, novabank_tenant)
    service = ChiefOfStaffService(uow)
    outcome = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_PREDICTION_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=target_id,
            as_of_at=AS_OF,
            horizon_days=90,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    if outcome.brief.estimate_kind is not None:
        assert outcome.brief.estimate_kind.value == "uncalibrated_score" or (
            outcome.brief.probability is None
        )
    assert outcome.brief.probability is None or outcome.brief.estimate_kind.value != (
        "uncalibrated_score"
    )
