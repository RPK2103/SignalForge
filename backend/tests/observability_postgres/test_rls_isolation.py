"""PostgreSQL RLS isolation proofs for Prompt 8 tables.

Runs as the NON-superuser application role. Uses ent_slo_definitions and
ent_alert_events as representative tenant-scoped Prompt 8 tables; the same
transaction-local GUC policy applies to every Prompt 8 table.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from tests.observability_postgres.conftest import assert_non_superuser

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
GUC = "signalforge.current_tenant_id"


def _set_tenant(conn, tenant: str) -> None:
    conn.execute(text(f"SELECT set_config('{GUC}', :t, true)"), {"t": tenant})


def _insert_slo(conn, tenant: str, key: str) -> None:
    conn.execute(
        text(
            "INSERT INTO ent_slo_definitions "
            "(id, tenant_id, slo_key, version, indicator, objective, comparison, unit, "
            "window_seconds, min_sample_count, description, schema_version, created_at) "
            "VALUES (:id, :t, :k, 1, 'api_5xx_free_ratio', 0.99, 'gte', 'ratio', "
            "86400, 20, 'desc', '1', now())"
        ),
        {"id": f"slo_{tenant}_{key}", "t": tenant, "k": key},
    )


def _count(conn) -> int:
    return conn.execute(text("SELECT count(*) FROM ent_slo_definitions")).scalar() or 0


def _seed_both(engine: Engine) -> None:
    with engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        _insert_slo(conn, TENANT_A, "avail")
    with engine.begin() as conn:
        _set_tenant(conn, TENANT_B)
        _insert_slo(conn, TENANT_B, "avail")


def test_application_role_is_not_superuser(app_engine: Engine):
    assert_non_superuser(app_engine)


def test_tenant_reads_own_rows(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        assert _count(conn) == 1


def test_select_isolation(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        rows = conn.execute(text("SELECT tenant_id FROM ent_slo_definitions")).scalars().all()
    assert set(rows) == {TENANT_A}


def test_missing_context_returns_no_rows(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        assert _count(conn) == 0


def test_insert_wrong_tenant_rejected(app_engine: Engine):
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        with pytest.raises(Exception):
            _insert_slo(conn, TENANT_B, "mallory")


def test_update_across_tenants_rejected(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        result = conn.execute(
            text("UPDATE ent_slo_definitions SET description = 'x' WHERE tenant_id = :t"),
            {"t": TENANT_B},
        )
        assert result.rowcount == 0


def test_delete_across_tenants_rejected(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        result = conn.execute(
            text("DELETE FROM ent_slo_definitions WHERE tenant_id = :t"), {"t": TENANT_B}
        )
        assert result.rowcount == 0


def test_connection_reuse_does_not_retain_tenant(app_engine: Engine):
    _seed_both(app_engine)
    with app_engine.connect() as conn:
        with conn.begin():
            _set_tenant(conn, TENANT_A)
            assert _count(conn) == 1
        with conn.begin():
            assert _count(conn) == 0


def test_alerts_table_isolation(app_engine: Engine):
    def _insert_alert(conn, tenant: str) -> None:
        conn.execute(
            text(
                "INSERT INTO ent_alert_events "
                "(id, tenant_id, fingerprint, severity, state, source, title, reason_code, "
                "opened_at, updated_at, transitions, event_metadata, schema_version, created_at) "
                "VALUES (:id, :t, :fp, 'critical', 'open', 'slo', 'x', 'slo_breached', "
                "now(), now(), '[]', '{}', '1', now())"
            ),
            {"id": f"al_{tenant}", "t": tenant, "fp": f"fp_{tenant}"},
        )

    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        _insert_alert(conn, TENANT_A)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_B)
        _insert_alert(conn, TENANT_B)
    with app_engine.begin() as conn:
        _set_tenant(conn, TENANT_A)
        rows = conn.execute(text("SELECT tenant_id FROM ent_alert_events")).scalars().all()
    assert set(rows) == {TENANT_A}
