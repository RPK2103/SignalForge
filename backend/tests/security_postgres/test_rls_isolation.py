"""PostgreSQL row-level-security isolation proofs (Phase 3 Prompt 7).

Every statement runs as the NON-superuser application role. Tenant context is
set transaction-locally via ``set_config`` and RLS policies compare against it.
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import Engine, text

from tests.security_postgres.conftest import assert_non_superuser

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
GUC = "signalforge.current_tenant_id"


def _set_tenant(conn, tenant: str) -> None:
    conn.execute(text(f"SELECT set_config('{GUC}', :t, true)"), {"t": tenant})


def _insert_principal(conn, tenant: str, subject: str) -> None:
    conn.execute(
        text(
            "INSERT INTO ent_security_principals "
            "(id, tenant_id, principal_type, external_subject_id, status, created_at) "
            "VALUES (:id, :tenant, 'user', :subject, 'active', now())"
        ),
        {"id": f"prn_{tenant}_{subject}", "tenant": tenant, "subject": subject},
    )


def _count(conn) -> int:
    return conn.execute(text("SELECT count(*) FROM ent_security_principals")).scalar() or 0


def _seed_both(engine: Engine) -> None:
    with engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        _insert_principal(conn, TENANT_A, "alice")
    with engine.begin() as conn:
        _set_tenant(conn, TENANT_B)
        _insert_principal(conn, TENANT_B, "bob")


def test_application_role_is_not_superuser(app_engine: Engine):
    assert_non_superuser(app_engine)


def test_tenant_reads_own_rows(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        assert _count(conn) == 1


def test_tenant_cannot_read_foreign_rows_direct_sql(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        rows = conn.execute(text("SELECT tenant_id FROM ent_security_principals")).scalars().all()
    assert set(rows) == {TENANT_A}


def test_missing_context_returns_no_rows(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        # No set_config -> current_setting is NULL -> policy matches nothing.
        assert _count(conn) == 0


def test_insert_wrong_tenant_rejected(app_engine: Engine):
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        with pytest.raises(Exception):
            _insert_principal(conn, TENANT_B, "mallory")


def test_update_across_tenants_rejected(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        result = conn.execute(
            text("UPDATE ent_security_principals SET display_label = 'x' WHERE tenant_id = :t"),
            {"t": TENANT_B},
        )
        assert result.rowcount == 0


def test_delete_across_tenants_rejected(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        result = conn.execute(
            text("DELETE FROM ent_security_principals WHERE tenant_id = :t"), {"t": TENANT_B}
        )
        assert result.rowcount == 0


def test_connection_reuse_does_not_retain_tenant(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.connect() as conn:
        with conn.begin():
            _set_tenant(conn, TENANT_A)
            assert _count(conn) == 1
        # New transaction on the SAME connection: context is gone -> no rows.
        with conn.begin():
            assert _count(conn) == 0


def test_rollback_does_not_leak_context(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.connect() as conn:
        trans = conn.begin()
        _set_tenant(conn, TENANT_A)
        assert _count(conn) == 1
        trans.rollback()
        with conn.begin():
            assert _count(conn) == 0


def test_concurrent_transactions_are_isolated(app_engine: Engine):
    _seed_both(app_engine)
    results: dict[str, set[str]] = {}
    barrier = threading.Barrier(2)

    def worker(tenant: str) -> None:
        with app_engine.connect() as conn:
            with conn.begin():
                _set_tenant(conn, tenant)
                barrier.wait(timeout=10)
                rows = (
                    conn.execute(text("SELECT tenant_id FROM ent_security_principals"))
                    .scalars()
                    .all()
                )
                results[tenant] = set(rows)

    threads = [threading.Thread(target=worker, args=(t,)) for t in (TENANT_A, TENANT_B)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results[TENANT_A] == {TENANT_A}
    assert results[TENANT_B] == {TENANT_B}
