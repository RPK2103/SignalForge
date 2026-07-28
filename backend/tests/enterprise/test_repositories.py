"""Repository tests: tenant isolation, pagination, evidence dedup, rollback."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import (
    DataSourceType,
    EnterpriseEntityType,
    EvidenceSignalType,
    OrganizationType,
)
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import CrossTenantAccessError, EnterpriseNotFoundError
from app.services.persistence.snapshot_service import snapshot_hash

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _org(ctx: TenantContext, slug: str = "nova") -> dm.Organization:
    return dm.Organization(
        organization_id=build_entity_id("org", ctx.tenant_id, slug),
        tenant_id=ctx.tenant_id,
        name="Nova",
        slug=slug,
        organization_type=OrganizationType.ENTERPRISE,
    )


def _data_source(ctx: TenantContext, name: str = "GitHub") -> dm.DataSource:
    return dm.DataSource(
        data_source_id=build_entity_id("ds", ctx.tenant_id, name),
        tenant_id=ctx.tenant_id,
        source_type=DataSourceType.GITHUB,
        display_name=name,
    )


def _evidence(ctx: TenantContext, ds_id: str, seq: int, payload: dict) -> dm.EvidenceSignal:
    payload_hash = snapshot_hash(payload)
    return dm.EvidenceSignal(
        evidence_signal_id=build_entity_id(
            "sig", ctx.tenant_id, ds_id, f"rec-{seq}", "commit", payload_hash
        ),
        tenant_id=ctx.tenant_id,
        data_source_id=ds_id,
        source_record_id=f"rec-{seq}",
        signal_type=EvidenceSignalType.COMMIT,
        subject_type=EnterpriseEntityType.REPOSITORY,
        subject_id="repo-1",
        event_time=_NOW,
        observed_at=_NOW,
        ingested_at=_NOW,
        payload=payload,
        payload_hash=payload_hash,
    )


def test_tenant_qualified_create_and_read(uow, tenant_a):
    org = _org(tenant_a)
    uow.organizations.add_organization(tenant_a, org)
    uow.commit()
    fetched = uow.organizations.get_organization(tenant_a, org.organization_id)
    assert fetched is not None
    assert fetched.tenant_id == "tenant-a"


def test_tenant_isolation_negative_lookup(uow, tenant_a, tenant_b):
    org = _org(tenant_a)
    uow.organizations.add_organization(tenant_a, org)
    uow.commit()
    # Tenant B cannot read tenant A's organization by id.
    assert uow.organizations.get_organization(tenant_b, org.organization_id) is None
    assert uow.organizations.get_tenant_organization(tenant_b) is None


def test_cross_tenant_association_rejected(uow, tenant_a, tenant_b):
    org = _org(tenant_a)
    uow.organizations.add_organization(tenant_a, org)
    uow.commit()
    bu = dm.BusinessUnit(
        business_unit_id=build_entity_id("bu", tenant_b.tenant_id, "retail"),
        tenant_id=tenant_b.tenant_id,
        organization_id=org.organization_id,  # belongs to tenant A
        name="Retail",
        code="retail",
        valid_from=_NOW,
    )
    with pytest.raises(CrossTenantAccessError):
        uow.organizations.add_business_unit(tenant_b, bu)


def test_pagination_is_deterministic(uow, tenant_a):
    ds_ids = []
    for i in range(5):
        ds = _data_source(tenant_a, f"src-{i}")
        uow.data_sources.add_data_source(tenant_a, ds)
        ds_ids.append(ds.data_source_id)
    uow.commit()
    page1 = uow.data_sources.list_data_sources(tenant_a, limit=2, offset=0)
    page2 = uow.data_sources.list_data_sources(tenant_a, limit=2, offset=2)
    assert page1.total == 5
    assert len(page1.items) == 2
    # Stable ordering: repeated calls return identical order.
    again = uow.data_sources.list_data_sources(tenant_a, limit=2, offset=0)
    assert [i.data_source_id for i in page1.items] == [i.data_source_id for i in again.items]
    assert {i.data_source_id for i in page1.items}.isdisjoint(
        {i.data_source_id for i in page2.items}
    )


def test_list_does_not_leak_other_tenant(uow, tenant_a, tenant_b):
    uow.data_sources.add_data_source(tenant_a, _data_source(tenant_a, "a-src"))
    uow.data_sources.add_data_source(tenant_b, _data_source(tenant_b, "b-src"))
    uow.commit()
    a_page = uow.data_sources.list_data_sources(tenant_a)
    assert a_page.total == 1
    assert a_page.items[0].tenant_id == "tenant-a"


def test_no_cross_tenant_update_of_ingestion_run(uow, tenant_a, tenant_b):
    uow.data_sources.add_data_source(tenant_a, _data_source(tenant_a))
    run = dm.IngestionRun(
        ingestion_run_id=build_entity_id("run", tenant_a.tenant_id, "r1"),
        tenant_id=tenant_a.tenant_id,
        data_source_id=build_entity_id("ds", tenant_a.tenant_id, "GitHub"),
    )
    uow.ingestion_runs.add_run(tenant_a, run)
    uow.commit()
    # Tenant B cannot update tenant A's run.
    with pytest.raises(EnterpriseNotFoundError):
        uow.ingestion_runs.update_run(tenant_b, run)


def test_evidence_append_and_retrieve(uow, tenant_a):
    uow.data_sources.add_data_source(tenant_a, _data_source(tenant_a))
    ds_id = build_entity_id("ds", tenant_a.tenant_id, "GitHub")
    signal = _evidence(tenant_a, ds_id, 1, {"kind": "commit", "n": 1})
    record, created = uow.evidence_signals.append(tenant_a, signal)
    uow.commit()
    assert created is True
    by_subject = uow.evidence_signals.list_by_subject(
        tenant_a, EnterpriseEntityType.REPOSITORY, "repo-1"
    )
    assert by_subject.total == 1
    by_source = uow.evidence_signals.list_by_source(tenant_a, ds_id)
    assert by_source.total == 1


def test_evidence_dedup_is_idempotent(uow, tenant_a):
    uow.data_sources.add_data_source(tenant_a, _data_source(tenant_a))
    ds_id = build_entity_id("ds", tenant_a.tenant_id, "GitHub")
    payload = {"kind": "commit", "sha": "abc"}
    s1 = _evidence(tenant_a, ds_id, 1, payload)
    r1, created1 = uow.evidence_signals.append(tenant_a, s1)
    uow.commit()
    s2 = _evidence(tenant_a, ds_id, 1, payload)
    r2, created2 = uow.evidence_signals.append(tenant_a, s2)
    uow.commit()
    assert created1 is True
    assert created2 is False
    assert r1.evidence_signal_id == r2.evidence_signal_id
    assert uow.evidence_signals.list_by_source(tenant_a, ds_id).total == 1


def test_transaction_rollback_leaves_no_partial_records(uow, tenant_a):
    def _op(u):
        u.organizations.add_organization(tenant_a, _org(tenant_a))
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        uow.execute(_op)
    assert uow.organizations.get_tenant_organization(tenant_a) is None
