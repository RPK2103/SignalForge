"""Service-layer tests: hierarchy, linkage, validation, ingestion, legacy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.enterprise_enums import (
    CapabilityCategory,
    DataSourceType,
    DependencyType,
    EnterpriseEntityType,
    EvidenceSignalType,
    IngestionRunStatus,
    OwnershipType,
)
from app.services.enterprise.enterprise_services import (
    DeliveryService,
    EnterpriseCatalogService,
    EnterpriseHierarchyService,
    IngestionService,
    InitiativeProjectService,
    RelationshipService,
)
from app.services.enterprise.exceptions import (
    CrossTenantAccessError,
    EnterpriseConflictError,
    EnterpriseNotFoundError,
    EnterpriseValidationError,
)
from app.services.enterprise.legacy_compat_service import LegacyCompatibilityService

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_one_organization_per_tenant_is_enforced(uow, tenant_a):
    svc = EnterpriseHierarchyService(uow)
    svc.create_organization(tenant_a, name="NovaBank")
    with pytest.raises(EnterpriseConflictError):
        svc.create_organization(tenant_a, name="Second Org")


def test_hierarchy_and_project_linkage(uow, tenant_a):
    hierarchy = EnterpriseHierarchyService(uow)
    initiatives = InitiativeProjectService(uow)
    org = hierarchy.create_organization(tenant_a, name="NovaBank")
    bu = hierarchy.create_business_unit(
        tenant_a, organization_id=org.organization_id, name="Retail", code="retail"
    )
    dept = hierarchy.create_department(
        tenant_a, business_unit_id=bu.business_unit_id, name="Payments", code="payments"
    )
    team = hierarchy.create_team(tenant_a, department_id=dept.department_id, name="Core")
    initiative = initiatives.create_initiative(
        tenant_a, organization_id=org.organization_id, name="Payment Modernization"
    )
    project = initiatives.create_project(
        tenant_a,
        name="Ledger Rewrite",
        initiative_id=initiative.initiative_id,
        owning_team_id=team.team_id,
    )
    assert project.initiative_id == initiative.initiative_id
    assert project.owning_team_id == team.team_id


def test_cross_tenant_initiative_reference_rejected(uow, tenant_a, tenant_b):
    hierarchy = EnterpriseHierarchyService(uow)
    initiatives = InitiativeProjectService(uow)
    org_a = hierarchy.create_organization(tenant_a, name="NovaBank")
    # Tenant B tries to create an initiative under tenant A's organization.
    with pytest.raises(CrossTenantAccessError):
        initiatives.create_initiative(tenant_b, organization_id=org_a.organization_id, name="Steal")


def test_dependency_self_reference_rejected(uow, tenant_a):
    svc = RelationshipService(uow)
    with pytest.raises(EnterpriseValidationError):
        svc.create_dependency(
            tenant_a,
            source_type=EnterpriseEntityType.PROJECT,
            source_id="p1",
            target_type=EnterpriseEntityType.PROJECT,
            target_id="p1",
            dependency_type=DependencyType.DEPENDS_ON,
        )


def test_ownership_creation(uow, tenant_a):
    svc = RelationshipService(uow)
    ownership = svc.create_ownership(
        tenant_a,
        owner_type=EnterpriseEntityType.TEAM,
        owner_id="team1",
        resource_type=EnterpriseEntityType.REPOSITORY,
        resource_id="repo1",
        ownership_type=OwnershipType.PRIMARY,
        allocation=100,
    )
    assert ownership.ownership_id.startswith("own_")


def test_availability_invalid_interval_rejected(uow, tenant_a):
    svc = RelationshipService(uow)
    with pytest.raises(ValidationError):
        svc.create_availability(
            tenant_a,
            target_type=EnterpriseEntityType.ENGINEER_PROFILE,
            target_id="eng1",
            start_time=_NOW,
            end_time=_NOW - timedelta(hours=1),
        )


def test_ingestion_run_state_transitions(uow, tenant_a):
    svc = IngestionService(uow)
    source = svc.register_data_source(
        tenant_a, source_type=DataSourceType.GITHUB, display_name="GitHub"
    )
    run = svc.start_run(tenant_a, data_source_id=source.data_source_id, run_key="r1")
    completed = svc.complete_run(
        tenant_a,
        ingestion_run_id=run.ingestion_run_id,
        status=IngestionRunStatus.SUCCEEDED,
        records_read=10,
        records_written=8,
    )
    assert completed.status is IngestionRunStatus.SUCCEEDED
    # Re-completing a terminal run is rejected.
    with pytest.raises(EnterpriseValidationError):
        svc.complete_run(
            tenant_a,
            ingestion_run_id=run.ingestion_run_id,
            status=IngestionRunStatus.SUCCEEDED,
        )


def test_complete_run_requires_terminal_status(uow, tenant_a):
    svc = IngestionService(uow)
    source = svc.register_data_source(
        tenant_a, source_type=DataSourceType.JIRA, display_name="Jira"
    )
    run = svc.start_run(tenant_a, data_source_id=source.data_source_id, run_key="r1")
    with pytest.raises(EnterpriseValidationError):
        svc.complete_run(
            tenant_a,
            ingestion_run_id=run.ingestion_run_id,
            status=IngestionRunStatus.RUNNING,
        )


def test_failed_run_persists_sanitized_error(uow, tenant_a):
    svc = IngestionService(uow)
    source = svc.register_data_source(
        tenant_a, source_type=DataSourceType.GITHUB, display_name="GitHub"
    )
    run = svc.start_run(tenant_a, data_source_id=source.data_source_id, run_key="r1")
    completed = svc.complete_run(
        tenant_a,
        ingestion_run_id=run.ingestion_run_id,
        status=IngestionRunStatus.FAILED,
        error_summary="connection failed token=supersecret",
    )
    assert "supersecret" not in (completed.error_summary or "")
    assert "redacted" in (completed.error_summary or "")


def test_evidence_provenance_and_dedup(uow, tenant_a):
    svc = IngestionService(uow)
    source = svc.register_data_source(
        tenant_a, source_type=DataSourceType.GITHUB, display_name="GitHub"
    )
    payload = {"sha": "abc123", "message": "fix"}
    signal, created = svc.append_evidence(
        tenant_a,
        data_source_id=source.data_source_id,
        source_record_id="commit-1",
        signal_type=EvidenceSignalType.COMMIT,
        subject_type=EnterpriseEntityType.REPOSITORY,
        subject_id="repo-1",
        payload=payload,
        event_time=_NOW,
    )
    assert created is True
    assert signal.provenance["recorded_by"] == "signalforge.ingestion_service"
    assert len(signal.payload_hash) == 64
    _, created_again = svc.append_evidence(
        tenant_a,
        data_source_id=source.data_source_id,
        source_record_id="commit-1",
        signal_type=EvidenceSignalType.COMMIT,
        subject_type=EnterpriseEntityType.REPOSITORY,
        subject_id="repo-1",
        payload=payload,
        event_time=_NOW,
    )
    assert created_again is False


def test_ingestion_run_not_found_for_tenant(uow, tenant_a):
    svc = IngestionService(uow)
    with pytest.raises(EnterpriseNotFoundError):
        svc.complete_run(
            tenant_a,
            ingestion_run_id="run_missing",
            status=IngestionRunStatus.SUCCEEDED,
        )


def test_partial_write_rolls_back_on_invalid_reference(uow, tenant_a):
    # A project referencing a non-existent team must roll back and leave no rows.
    initiatives = InitiativeProjectService(uow)
    with pytest.raises(CrossTenantAccessError):
        initiatives.create_project(tenant_a, name="Orphan", owning_team_id="team_missing")
    assert initiatives.list_projects(tenant_a).total == 0


def test_capability_catalog(uow, tenant_a):
    svc = EnterpriseCatalogService(uow)
    cap = svc.create_capability(tenant_a, name="Cloud Migration", category=CapabilityCategory.CLOUD)
    assert cap.slug == "cloud-migration"
    assert svc.list_capabilities(tenant_a).total == 1


def test_delivery_repository_registration(uow, tenant_a):
    svc = DeliveryService(uow)
    repo = svc.register_repository(tenant_a, name="ledger", external_reference="novabank/ledger")
    assert repo.repository_id.startswith("repo_")
    assert svc.list_repositories(tenant_a).total == 1


def test_legacy_projection_is_tenant_scoped(seeded_db, novabank_tenant, tenant_b):
    from sqlalchemy.orm import Session

    from app.db.session import get_engine

    engine = get_engine(seeded_db)
    with Session(engine) as session:
        from app.db.unit_of_work import UnitOfWork

        uow = UnitOfWork(session)
        svc = LegacyCompatibilityService(uow)
        # Tenant B (no legacy rows) sees an empty projection; no cross-tenant leak.
        empty = svc.project_catalog(tenant_b)
        assert empty.project_count == 0
        assert empty.engineer_count == 0
    engine.dispose()
