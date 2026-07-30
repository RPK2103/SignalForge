"""Cross-dialect Alembic version-table width (Phase 3 Prompt 7 remediation).

Several Phase 3 revision identifiers exceed Alembic's default
``alembic_version.version_num VARCHAR(32)`` column — for example
``p3_continuous_scenario_intelligence`` (35 chars) and
``p3_connector_ingestion_foundation`` (33 chars). On SQLite the VARCHAR length is
not enforced, so this defect was latent; on PostgreSQL the ``INSERT`` of the
revision id into the version table fails, blocking every migration.

Rather than renaming historical revisions, we widen the version column to
``VARCHAR(128)`` for NEW databases using Alembic's documented
``DefaultImpl.version_table_impl`` hook (public extension point since Alembic
1.14). Alembic consults this hook to build the version ``Table`` for BOTH online
migrations and offline ``--sql`` generation, so the wider column appears in every
mode without touching Alembic internals.

For an EXISTING PostgreSQL database whose version column is still the narrower
width, :func:`widen_existing_version_table` widens it in place — it never drops,
recreates or truncates the table.
"""

from __future__ import annotations

from alembic.ddl.impl import DefaultImpl
from sqlalchemy import Column, MetaData, PrimaryKeyConstraint, String, Table, inspect, text
from sqlalchemy.engine import Connection

# Comfortably wider than the longest current revision id, with headroom.
VERSION_NUM_WIDTH = 128


def _wide_version_table_impl(
    self: DefaultImpl,
    *,
    version_table: str,
    version_table_schema: str | None,
    version_table_pk: bool,
    **kw: object,
) -> Table:
    """Alembic ``version_table_impl`` hook producing a wide ``version_num`` column."""
    vt = Table(
        version_table,
        MetaData(),
        Column("version_num", String(VERSION_NUM_WIDTH), nullable=False),
        schema=version_table_schema,
    )
    if version_table_pk:
        vt.append_constraint(PrimaryKeyConstraint("version_num", name=f"{version_table}_pkc"))
    return vt


def install_wide_version_table() -> None:
    """Install the widened version-table hook (idempotent).

    Overrides the documented ``DefaultImpl.version_table_impl`` extension hook so
    every dialect (PostgreSQL and SQLite both inherit it) builds the version table
    with a ``VARCHAR(128)`` ``version_num`` column.
    """
    DefaultImpl.version_table_impl = _wide_version_table_impl  # type: ignore[method-assign]


def widen_existing_version_table(
    connection: Connection, *, version_table: str = "alembic_version"
) -> None:
    """Widen an existing narrower PostgreSQL version column in place.

    No-op unless the dialect enforces VARCHAR length (PostgreSQL) and the version
    table already exists. Never recreates or truncates the table, so it is safe to
    run on every startup/migration.
    """
    if connection.dialect.name != "postgresql":
        return
    inspector = inspect(connection)
    if not inspector.has_table(version_table):
        return
    connection.execute(
        text(
            f"ALTER TABLE {version_table} "
            f"ALTER COLUMN version_num TYPE VARCHAR({VERSION_NUM_WIDTH})"
        )
    )
