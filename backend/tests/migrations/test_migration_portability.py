"""Cross-dialect migration-portability tests (Phase 3 Prompt 7 remediation).

These prove — without requiring a live PostgreSQL server — that the three
migration-chain defects the independent audit found are corrected:

1. long Alembic revision ids fit the version table (VARCHAR(128));
2. the Prompt 4 Boolean check compiles to portable SQL (no ``= 1`` against a
   Boolean column);
3. the Prompt 5 Boolean default compiles to ``DEFAULT false`` on PostgreSQL.

The offline-SQL assertions use Alembic's own ``--sql`` generation against the
PostgreSQL dialect, so they exercise the real compilation path.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout

import pytest
from alembic.config import Config
from sqlalchemy import String

from app.db.alembic_version_table import (
    VERSION_NUM_WIDTH,
    _wide_version_table_impl,
    install_wide_version_table,
)

_PG_URL = "postgresql://user:pass@localhost/signalforge_offline"


@pytest.fixture(scope="module")
def offline_pg_sql() -> str:
    """Generate the full base→head migration SQL for the PostgreSQL dialect."""
    install_wide_version_table()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _PG_URL)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        from alembic import command

        command.upgrade(cfg, "head", sql=True)
    return buffer.getvalue()


def test_version_table_hook_widens_column():
    install_wide_version_table()
    table = _wide_version_table_impl(
        object(),  # type: ignore[arg-type]
        version_table="alembic_version",
        version_table_schema=None,
        version_table_pk=True,
    )
    column = table.c.version_num
    assert isinstance(column.type, String)
    assert column.type.length == VERSION_NUM_WIDTH == 128


def test_offline_version_table_is_wide(offline_pg_sql: str):
    assert f"version_num VARCHAR({VERSION_NUM_WIDTH})" in offline_pg_sql


def test_long_revision_ids_are_recorded(offline_pg_sql: str):
    # The longest ids exceed the historical VARCHAR(32) default.
    for revision in (
        "p3_continuous_scenario_intelligence",
        "p3_connector_ingestion_foundation",
    ):
        assert len(revision) > 32
        assert revision in offline_pg_sql


def test_boolean_check_is_portable(offline_pg_sql: str):
    # Corrected Prompt 4 constraint: no numeric comparison against a Boolean column.
    assert "production_eligible = 1" not in offline_pg_sql
    assert "NOT (data_scope = 'synthetic' AND production_eligible)" in offline_pg_sql


def test_boolean_default_is_portable(offline_pg_sql: str):
    # Corrected Prompt 5 default + check: dialect-safe Boolean on PostgreSQL.
    assert "training_eligible = 0" not in offline_pg_sql
    assert "training_eligible BOOLEAN DEFAULT false NOT NULL" in offline_pg_sql
    assert "CHECK (NOT training_eligible)" in offline_pg_sql
