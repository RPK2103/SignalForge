"""Adversarial and transactional tests for NovaBank demo seed."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.models import enterprise as orm
from app.demo.novabank.constants import DATASET_VERSION, TENANT_ID
from app.demo.novabank.helpers import tid
from app.demo.novabank.service import NovaBankDemoService
from app.security.audit import AuditWriteError
from app.security.context import internal_system_context
from app.security.enums import Permission, SecurityRole
from app.security.exceptions import AuthorizationError
from app.security.permissions import permissions_for_roles


def test_wrong_tenant_denied(demo_session: Session):
    security = internal_system_context(
        "other-tenant",
        correlation_id="wrong-tenant",
        roles=frozenset({SecurityRole.TENANT_ADMIN}),
        permissions=permissions_for_roles(frozenset({SecurityRole.TENANT_ADMIN})),
    )
    service = NovaBankDemoService(demo_session, security)
    with pytest.raises(AuthorizationError):
        service.seed()


def test_injected_failure_rolls_back(demo_session: Session, demo_security, monkeypatch):
    from sqlalchemy import select

    from app.demo.novabank import service as svc_mod

    def fail_scenarios(session):
        raise RuntimeError("injected_generation_failure")

    monkeypatch.setattr(svc_mod, "seed_story_scenarios", fail_scenarios)
    service = NovaBankDemoService(demo_session, demo_security)
    with pytest.raises(RuntimeError, match="injected_generation_failure"):
        service.seed()
    demo_session.expire_all()
    orgs = demo_session.scalars(
        select(orm.Organization).where(orm.Organization.tenant_id == TENANT_ID)
    ).all()
    assert orgs == []


def test_audit_failure_blocks_success(demo_session: Session, demo_security, monkeypatch):
    from sqlalchemy import select

    service = NovaBankDemoService(demo_session, demo_security)

    def fail_audit(*args, **kwargs):
        raise AuditWriteError("injected_audit_failure")

    monkeypatch.setattr(service._audit, "record_sensitive_action", fail_audit)
    with pytest.raises(AuditWriteError):
        service.seed()
    demo_session.expire_all()
    orgs = demo_session.scalars(
        select(orm.Organization).where(orm.Organization.tenant_id == TENANT_ID)
    ).all()
    assert orgs == []


def test_incompatible_manifest_rejected(demo_session: Session, demo_security, seeded_demo):
    # Corrupt stored manifest hash.
    from sqlalchemy import select

    from app.demo.novabank.constants import MANIFEST_SIGNAL_TYPE, MANIFEST_SOURCE_RECORD_ID

    row = demo_session.scalars(
        select(orm.EvidenceSignal).where(
            orm.EvidenceSignal.tenant_id == TENANT_ID,
            orm.EvidenceSignal.signal_type == MANIFEST_SIGNAL_TYPE,
            orm.EvidenceSignal.source_record_id == MANIFEST_SOURCE_RECORD_ID,
        )
    ).one()
    payload = dict(row.payload)
    payload["manifest_hash"] = "0" * 64
    row.payload = payload
    demo_session.flush()
    with pytest.raises(ValueError, match="Incompatible"):
        NovaBankDemoService(demo_session, demo_security).seed()


def test_permission_matrix_includes_demo_manage():
    perms = permissions_for_roles(frozenset({SecurityRole.TENANT_ADMIN}))
    assert Permission.DEMO_TENANT_MANAGE in perms
    reader = permissions_for_roles(frozenset({SecurityRole.EXECUTIVE_READER}))
    assert Permission.DEMO_TENANT_MANAGE not in reader


def test_dataset_version_constant():
    assert DATASET_VERSION == "novabank-enterprise-demo-v2"
    assert tid("org", "novabank").startswith("org_")
