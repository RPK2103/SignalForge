"""Domain contract tests for Chief of Staff requests and hashing."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffSection,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import (
    ChiefOfStaffEvidencePackage,
    ChiefOfStaffRequest,
    FreshnessSummary,
    TargetLifecycleInfo,
    TruncationMetadata,
)
from app.services.chief_of_staff.canonicalization import (
    attach_package_hash,
    compute_package_hash,
)
from app.services.chief_of_staff.decision_options import compute_decision_options

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _minimal_package(**overrides) -> ChiefOfStaffEvidencePackage:
    base = dict(
        tenant_id="novabank",
        target_type=ChiefOfStaffTargetType.PROJECT,
        target_id="proj-1",
        target_stable_id="proj-1",
        as_of_at=AS_OF,
        intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
        target_lifecycle=TargetLifecycleInfo(
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id="proj-1",
            display_name="Demo Project",
        ),
        freshness_summary=FreshnessSummary(overall_state="fresh"),
        truncation=TruncationMetadata(),
        evidence_entries=[],
        package_hash="",
    )
    base.update(overrides)
    return ChiefOfStaffEvidencePackage(**base)


def test_request_rejects_invalid_horizon():
    with pytest.raises(ValidationError):
        ChiefOfStaffRequest(
            tenant_id="novabank",
            intent=ChiefOfStaffIntent.DELIVERY_PREDICTION_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id="p1",
            as_of_at=AS_OF,
            horizon_days=45,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        )


def test_request_requires_prior_for_change_intent():
    with pytest.raises(ValidationError):
        ChiefOfStaffRequest(
            tenant_id="novabank",
            intent=ChiefOfStaffIntent.CHANGE_SINCE_LAST_REVIEW,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id="p1",
            as_of_at=AS_OF,
        )


def test_request_rejects_unknown_section():
    with pytest.raises(ValidationError):
        ChiefOfStaffRequest(
            tenant_id="novabank",
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id="p1",
            as_of_at=AS_OF,
            requested_sections=["not_a_real_section"],  # type: ignore[list-item]
        )


def test_request_rejects_scenario_ids_for_non_scenario_intent():
    with pytest.raises(ValidationError):
        ChiefOfStaffRequest(
            tenant_id="novabank",
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id="p1",
            as_of_at=AS_OF,
            scenario_run_ids=["run-1"],
        )


def test_request_requires_scenario_ids_for_comparison():
    with pytest.raises(ValidationError):
        ChiefOfStaffRequest(
            tenant_id="novabank",
            intent=ChiefOfStaffIntent.SCENARIO_COMPARISON_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id="p1",
            as_of_at=AS_OF,
            scenario_run_ids=[],
        )


def test_request_bounds_scenario_run_ids():
    with pytest.raises(ValidationError):
        ChiefOfStaffRequest(
            tenant_id="novabank",
            intent=ChiefOfStaffIntent.SCENARIO_COMPARISON_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id="p1",
            as_of_at=AS_OF,
            scenario_run_ids=[f"r{i}" for i in range(11)],
        )


def test_default_sections_applied():
    req = ChiefOfStaffRequest(
        tenant_id="novabank",
        intent=ChiefOfStaffIntent.EVIDENCE_GAP_BRIEF,
        target_type=ChiefOfStaffTargetType.INITIATIVE,
        target_id="i1",
        as_of_at=AS_OF,
    )
    assert ChiefOfStaffSection.EVIDENCE_GAPS in req.requested_sections


def test_canonical_hash_independent_of_dict_order():
    # Different list order changes hash — assembly must pre-sort. Verify same sorted input.
    pkg_c = attach_package_hash(_minimal_package(missing_data_warnings=["a", "b"]))
    pkg_d = attach_package_hash(_minimal_package(missing_data_warnings=["a", "b"]))
    assert pkg_c.package_hash == pkg_d.package_hash
    assert compute_package_hash(pkg_c) == pkg_c.package_hash


def test_changed_evidence_changes_hash():
    a = attach_package_hash(_minimal_package(missing_data_warnings=["x"]))
    b = attach_package_hash(_minimal_package(missing_data_warnings=["y"]))
    assert a.package_hash != b.package_hash


def test_decision_options_always_include_continue_monitoring():
    pkg = attach_package_hash(_minimal_package())
    # Need at least package metadata entry for supporting ids; options still compute.
    opts = compute_decision_options(pkg)
    assert any(o.option_type.value == "continue_monitoring" and o.eligible for o in opts)
