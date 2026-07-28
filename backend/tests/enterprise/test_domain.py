"""Domain-model tests: validation, temporal intervals, enums, identifiers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import (
    AvailabilityReason,
    DependencyType,
    EnterpriseEntityType,
)
from app.domain.enterprise_identifiers import build_entity_id, slugify
from app.domain.enterprise_models import FORBIDDEN_ENGINEER_FIELDS
from app.domain.tenant_context import InvalidTenantContextError, TenantContext

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _bu(**overrides):
    base = dict(
        business_unit_id="bu_1",
        tenant_id="tenant-a",
        organization_id="org_1",
        name="Retail",
        code="retail",
        valid_from=_NOW,
    )
    base.update(overrides)
    return dm.BusinessUnit(**base)


def test_business_unit_valid_interval_rejected_when_end_before_start():
    with pytest.raises(ValidationError):
        _bu(valid_to=_NOW - timedelta(days=1))


def test_business_unit_open_interval_allowed():
    bu = _bu(valid_to=None)
    assert bu.valid_to is None


def test_sprint_requires_strictly_increasing_interval():
    with pytest.raises(ValidationError):
        dm.Sprint(
            sprint_id="s1",
            tenant_id="t",
            team_id="team1",
            name="Sprint 1",
            start_time=_NOW,
            end_time=_NOW,  # equal -> invalid (strict)
        )


def test_availability_end_must_exceed_start():
    with pytest.raises(ValidationError):
        dm.Availability(
            availability_id="a1",
            tenant_id="t",
            target_type=EnterpriseEntityType.ENGINEER_PROFILE,
            target_id="eng1",
            start_time=_NOW,
            end_time=_NOW - timedelta(hours=1),
            reason=AvailabilityReason.PLANNED_LEAVE,
        )


def test_deployment_completion_must_not_precede_start():
    with pytest.raises(ValidationError):
        dm.Deployment(
            deployment_id="d1",
            tenant_id="t",
            started_at=_NOW,
            completed_at=_NOW - timedelta(minutes=1),
            external_reference="deploy-1",
        )


def test_incident_resolution_must_not_precede_start():
    with pytest.raises(ValidationError):
        dm.Incident(
            incident_id="i1",
            tenant_id="t",
            started_at=_NOW,
            resolved_at=_NOW - timedelta(minutes=1),
            external_reference="INC-1",
        )


def test_dependency_rejects_self_reference():
    with pytest.raises(ValidationError):
        dm.Dependency(
            dependency_id="dep1",
            tenant_id="t",
            source_type=EnterpriseEntityType.PROJECT,
            source_id="p1",
            target_type=EnterpriseEntityType.PROJECT,
            target_id="p1",
            dependency_type=DependencyType.DEPENDS_ON,
            valid_from=_NOW,
        )


def test_naive_datetime_interval_validation_does_not_raise():
    # Naive datetimes are assumed UTC by the interval validator (SQLite reads
    # return naive datetimes); constructing with naive bounds must not raise.
    bu = _bu(valid_from=datetime(2026, 1, 1), valid_to=datetime(2026, 2, 1))
    assert bu.valid_to > bu.valid_from


def test_confidence_bounds_enforced():
    with pytest.raises(ValidationError):
        dm.EngineerCapabilityEvidence(
            evidence_id="e1",
            tenant_id="t",
            engineer_profile_id="eng1",
            capability_id="cap1",
            confidence=1.5,
            valid_from=_NOW,
        )


def test_engineer_profile_forbids_sensitive_attributes():
    # extra="forbid" must reject any sensitive field injection attempt.
    for field in ["gender", "ethnicity", "salary", "age", "health"]:
        with pytest.raises(ValidationError):
            dm.EngineerProfile(
                engineer_profile_id="eng1",
                tenant_id="t",
                display_name="Fictional Person",
                valid_from=_NOW,
                **{field: "x"},
            )


def test_forbidden_fields_absent_from_engineer_profile_schema():
    fields = set(dm.EngineerProfile.model_fields.keys())
    assert not (fields & FORBIDDEN_ENGINEER_FIELDS)


def test_identifier_is_deterministic_and_tenant_scoped():
    a1 = build_entity_id("team", "tenant-a", "payments")
    a2 = build_entity_id("team", "tenant-a", "payments")
    b1 = build_entity_id("team", "tenant-b", "payments")
    assert a1 == a2  # stable
    assert a1 != b1  # tenant-scoped uniqueness
    assert a1.startswith("team_")


def test_slugify_bounds_and_normalizes():
    assert slugify("Payments Core!") == "payments-core"
    assert len(slugify("x" * 200)) <= 64


def test_tenant_context_normalizes_and_rejects_blank():
    assert TenantContext.require("Tenant-A").tenant_id == "tenant-a"
    with pytest.raises(InvalidTenantContextError):
        TenantContext.require("")
    with pytest.raises(InvalidTenantContextError):
        TenantContext.require(None)
    with pytest.raises(InvalidTenantContextError):
        TenantContext.require("bad tenant id!")
