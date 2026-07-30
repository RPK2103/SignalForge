"""PostgreSQL Row-Level Security helpers (Phase 3 Prompt 7).

Defense in depth on top of the tenant-scoped repository layer. RLS is
PostgreSQL-specific; on SQLite these helpers are no-ops and isolation relies on
the application layer (SQLite is NOT proof of RLS).

Request-scoped tenant context is set transaction-locally via ``set_config`` so a
pooled connection never retains another request's tenant, and a rollback clears
it automatically. Missing context fails closed: ``current_setting(guc, true)``
returns NULL, and ``tenant_id = NULL`` is NULL, so no rows match.
"""

from __future__ import annotations

from sqlalchemy import MetaData, text
from sqlalchemy.orm import Session

# Transaction-local GUC that RLS policies compare against.
TENANT_GUC = "signalforge.current_tenant_id"
_TENANT_COLUMN = "tenant_id"

# The audit log keeps a nullable tenant only for pre-tenant authentication
# failures; those global rows are intentionally invisible to tenant-scoped RLS
# reads (they are queried by the privileged migration/admin role only).
AUDIT_TABLE = "ent_security_audit_events"


def tenant_rls_tables(metadata: MetaData) -> list[str]:
    """Reviewed list of tenant-qualified tables that receive forced RLS.

    Derived from the ORM metadata: any table with a NOT NULL ``tenant_id``
    column. This deterministically includes every ``ent_*`` tenant table and the
    new security tables, and excludes legacy tables whose ``tenant_id`` is
    nullable (compatibility rows) or absent.
    """
    tables: list[str] = []
    for table in metadata.sorted_tables:
        column = table.columns.get(_TENANT_COLUMN)
        if column is None:
            continue
        if column.nullable:
            continue
        tables.append(table.name)
    return tables


def rls_policy_statements(table: str) -> list[str]:
    """DDL to enable + force RLS and install a tenant-isolation policy."""
    policy_name = f"{table}_tenant_isolation"
    predicate = f"{_TENANT_COLUMN} = current_setting('{TENANT_GUC}', true)"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        # FORCE applies RLS even to the table owner, so the application role can
        # never accidentally bypass isolation via ownership.
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {policy_name} ON {table}",
        (f"CREATE POLICY {policy_name} ON {table} USING ({predicate}) WITH CHECK ({predicate})"),
    ]


def audit_rls_policy_statements() -> list[str]:
    """RLS for the audit log: NULL-tenant global rows are never tenant-visible."""
    table = AUDIT_TABLE
    policy_name = f"{table}_tenant_isolation"
    predicate = (
        f"{_TENANT_COLUMN} IS NOT NULL AND {_TENANT_COLUMN} = current_setting('{TENANT_GUC}', true)"
    )
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {policy_name} ON {table}",
        (f"CREATE POLICY {policy_name} ON {table} USING ({predicate}) WITH CHECK ({predicate})"),
    ]


def rls_disable_statements(table: str) -> list[str]:
    policy_name = f"{table}_tenant_isolation"
    return [
        f"DROP POLICY IF EXISTS {policy_name} ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]


def is_postgres(session: Session) -> bool:
    return session.bind is not None and session.bind.dialect.name == "postgresql"


def set_transaction_tenant(session: Session, tenant_id: str) -> None:
    """Set the transaction-local tenant GUC (PostgreSQL only)."""
    if not is_postgres(session):
        return
    session.execute(
        text(f"SELECT set_config('{TENANT_GUC}', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def clear_transaction_tenant(session: Session) -> None:
    """Clear the transaction-local tenant GUC so no context leaks (PostgreSQL)."""
    if not is_postgres(session):
        return
    session.execute(text(f"SELECT set_config('{TENANT_GUC}', '', true)"))


def current_transaction_tenant(session: Session) -> str | None:
    if not is_postgres(session):
        return None
    value = session.execute(text(f"SELECT current_setting('{TENANT_GUC}', true)")).scalar()
    return value or None
