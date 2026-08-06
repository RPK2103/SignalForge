"""UnitOfWork tenant-scoped execution boundaries (Prompt 9 RLS hardening).

Proves ``execute_for_tenant`` applies transaction-local tenant context before
the callback, and that commit/rollback paths re-apply on the next execute.
SQLite remains valid (RLS helpers are no-ops). Non-tenant ``execute`` is
unchanged.
"""

from __future__ import annotations

import pytest

from app.db.unit_of_work import UnitOfWork
from app.domain.tenant_context import InvalidTenantContextError


def test_execute_for_tenant_applies_context_before_callback(unit_of_work, monkeypatch):
    calls: list[str] = []

    def _set(session, tenant_id: str) -> None:
        calls.append(f"set:{tenant_id}")

    monkeypatch.setattr("app.db.unit_of_work.set_transaction_tenant", _set)

    def _run(inner: UnitOfWork) -> str:
        calls.append("callback")
        return "ok"

    assert unit_of_work.execute_for_tenant("novabank", _run) == "ok"
    assert calls == ["set:novabank", "callback"]


def test_execute_for_tenant_reapplies_after_commit(unit_of_work, monkeypatch):
    applied: list[str] = []

    def _set(session, tenant_id: str) -> None:
        applied.append(tenant_id)

    monkeypatch.setattr("app.db.unit_of_work.set_transaction_tenant", _set)

    unit_of_work.execute_for_tenant("novabank", lambda _u: 1)
    unit_of_work.execute_for_tenant("novabank", lambda _u: 2)
    assert applied == ["novabank", "novabank"]


def test_execute_for_tenant_reapplies_after_rollback(unit_of_work, monkeypatch):
    applied: list[str] = []

    def _set(session, tenant_id: str) -> None:
        applied.append(tenant_id)

    monkeypatch.setattr("app.db.unit_of_work.set_transaction_tenant", _set)

    def _boom(_u: UnitOfWork) -> None:
        raise RuntimeError("forced failure")

    with pytest.raises(RuntimeError, match="forced failure"):
        unit_of_work.execute_for_tenant("novabank", _boom)

    assert unit_of_work.execute_for_tenant("novabank", lambda _u: "recovered") == "recovered"
    assert applied == ["novabank", "novabank"]


def test_execute_for_tenant_rejects_blank_tenant(unit_of_work):
    with pytest.raises(InvalidTenantContextError):
        unit_of_work.execute_for_tenant("  ", lambda _u: None)


def test_plain_execute_does_not_set_tenant(unit_of_work, monkeypatch):
    calls: list[str] = []

    def _set(session, tenant_id: str) -> None:
        calls.append(tenant_id)

    monkeypatch.setattr("app.db.unit_of_work.set_transaction_tenant", _set)
    assert unit_of_work.execute(lambda _u: "legacy") == "legacy"
    assert calls == []


def test_execute_for_tenant_sqlite_roundtrip(unit_of_work):
    """SQLite path: SET LOCAL is a no-op; execute_for_tenant still commits."""
    seen: list[int] = []

    def _run(inner: UnitOfWork) -> int:
        seen.append(1)
        return 42

    assert unit_of_work.execute_for_tenant("tenant-a", _run) == 42
    assert seen == [1]
