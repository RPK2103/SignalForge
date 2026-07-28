"""Concurrency / cross-session idempotency and isolation tests."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_enums import (
    DataSourceType,
    EnterpriseEntityType,
    EvidenceSignalType,
)
from app.domain.tenant_context import TenantContext
from app.services.enterprise.enterprise_services import (
    EnterpriseHierarchyService,
    IngestionService,
)

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_TENANT_A = TenantContext.require("tenant-a")
_TENANT_B = TenantContext.require("tenant-b")


@contextmanager
def _session(url: str):
    engine = get_engine(url)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _append(session: Session, ctx: TenantContext, ds_id: str, payload: dict):
    svc = IngestionService(UnitOfWork(session))
    return svc.append_evidence(
        ctx,
        data_source_id=ds_id,
        source_record_id="rec-1",
        signal_type=EvidenceSignalType.COMMIT,
        subject_type=EnterpriseEntityType.REPOSITORY,
        subject_id="repo-1",
        payload=payload,
        event_time=_NOW,
    )


def test_evidence_idempotent_across_independent_sessions(migrated_db):
    payload = {"sha": "abc", "kind": "commit"}
    with _session(migrated_db) as s1:
        ds = IngestionService(UnitOfWork(s1)).register_data_source(
            _TENANT_A, source_type=DataSourceType.GITHUB, display_name="GitHub"
        )
        _, created1 = _append(s1, _TENANT_A, ds.data_source_id, payload)
    # A second, independent session appends the identical signal.
    with _session(migrated_db) as s2:
        _, created2 = _append(s2, _TENANT_A, ds.data_source_id, payload)
    assert created1 is True
    assert created2 is False
    # Exactly one row persisted.
    with _session(migrated_db) as s3:
        page = UnitOfWork(s3).evidence_signals.list_by_source(_TENANT_A, ds.data_source_id)
    assert page.total == 1


def test_true_concurrent_duplicate_evidence_yields_single_row(migrated_db):
    """Genuinely concurrent (thread + barrier) duplicate appends of the same
    dedup tuple must produce exactly one row, exactly one created=True, and must
    not poison any session or leak an unhandled IntegrityError."""
    with _session(migrated_db) as s0:
        ds = IngestionService(UnitOfWork(s0)).register_data_source(
            _TENANT_A, source_type=DataSourceType.GITHUB, display_name="GitHub"
        )
    ds_id = ds.data_source_id
    payload = {"kind": "commit", "sha": "deadbeef"}

    worker_count = 4
    barrier = threading.Barrier(worker_count)
    created_flags: list[bool] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait(timeout=15)
            with _session(migrated_db) as s:
                _, created = _append(s, _TENANT_A, ds_id, payload)
            with lock:
                created_flags.append(created)
        except Exception as exc:  # noqa: BLE001 - record for assertion
            with lock:
                errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=worker) for _ in range(worker_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"unexpected errors under concurrency: {errors}"
    assert sum(1 for c in created_flags if c) == 1, created_flags
    with _session(migrated_db) as s_final:
        page = UnitOfWork(s_final).evidence_signals.list_by_source(_TENANT_A, ds_id)
    assert page.total == 1


def test_concurrent_tenant_operations_remain_isolated(migrated_db):
    with _session(migrated_db) as s1:
        EnterpriseHierarchyService(UnitOfWork(s1)).create_organization(_TENANT_A, name="Alpha Corp")
    with _session(migrated_db) as s2:
        EnterpriseHierarchyService(UnitOfWork(s2)).create_organization(_TENANT_B, name="Beta Corp")
    with _session(migrated_db) as s3:
        uow = UnitOfWork(s3)
        org_a = uow.organizations.get_tenant_organization(_TENANT_A)
        org_b = uow.organizations.get_tenant_organization(_TENANT_B)
    assert org_a is not None and org_a.name == "Alpha Corp"
    assert org_b is not None and org_b.name == "Beta Corp"
    assert org_a.organization_id != org_b.organization_id
