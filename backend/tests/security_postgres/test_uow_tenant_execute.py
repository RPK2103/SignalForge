"""PostgreSQL FORCE RLS proofs for UnitOfWork.execute_for_tenant."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.unit_of_work import UnitOfWork
from app.security.rls import TENANT_GUC, current_transaction_tenant, set_transaction_tenant

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def _insert_principal(session: Session, tenant: str, subject: str) -> None:
    session.execute(
        text(
            "INSERT INTO ent_security_principals "
            "(id, tenant_id, principal_type, external_subject_id, status, created_at) "
            "VALUES (:id, :tenant, 'user', :subject, 'active', now())"
        ),
        {"id": f"prn_uow_{tenant}_{subject}", "tenant": tenant, "subject": subject},
    )


def _count(session: Session) -> int:
    return int(session.execute(text("SELECT count(*) FROM ent_security_principals")).scalar() or 0)


def test_execute_for_tenant_sets_guc_before_callback(app_engine):
    session = Session(app_engine)
    try:
        uow = UnitOfWork(session)

        def _seed(inner: UnitOfWork) -> int:
            assert current_transaction_tenant(inner.session) == TENANT_A
            _insert_principal(inner.session, TENANT_A, "alice")
            return _count(inner.session)

        assert uow.execute_for_tenant(TENANT_A, _seed) == 1

        # Commit cleared SET LOCAL; missing context sees no rows.
        assert current_transaction_tenant(session) in (None, "")
        assert _count(session) == 0

        def _reread(inner: UnitOfWork) -> int:
            return _count(inner.session)

        assert uow.execute_for_tenant(TENANT_A, _reread) == 1
        assert uow.execute_for_tenant(TENANT_B, _reread) == 0
    finally:
        session.close()


def test_execute_for_tenant_after_commit_isolates_wrong_tenant(app_engine):
    session = Session(app_engine)
    try:
        uow = UnitOfWork(session)
        uow.execute_for_tenant(
            TENANT_A, lambda inner: _insert_principal(inner.session, TENANT_A, "bob")
        )
        # Prior execute committed; next execute must re-apply GUC.
        visible = uow.execute_for_tenant(TENANT_A, lambda inner: _count(inner.session))
        assert visible == 1
        foreign = uow.execute_for_tenant(TENANT_B, lambda inner: _count(inner.session))
        assert foreign == 0
    finally:
        session.close()


def test_missing_guc_hides_rows_after_plain_commit(app_engine):
    session = Session(app_engine)
    try:
        set_transaction_tenant(session, TENANT_A)
        _insert_principal(session, TENANT_A, "carol")
        session.commit()
        # New transaction, no GUC → FORCE RLS hides own-tenant rows.
        assert _count(session) == 0
        guc = session.execute(text(f"SELECT current_setting('{TENANT_GUC}', true)")).scalar()
        assert not guc
    finally:
        session.close()
