"""Append-only security audit + redaction tests (Phase 3 Prompt 7)."""

from __future__ import annotations

import pytest

from app.security.audit import AuditWriteError, SecurityAuditService
from app.security.context import SecurityContext
from app.security.enums import (
    AuthenticationFailureCategory,
    AuthenticationMode,
    Permission,
    PrincipalType,
    SecurityAuditAction,
    SecurityRole,
)
from app.security.permissions import permissions_for_roles
from app.security.principal import AuthenticatedPrincipal
from app.security.redaction import contains_secret, hash_identifier, sanitize_metadata

TENANT = "novabank"


def _context() -> SecurityContext:
    roles = frozenset({SecurityRole.TENANT_ADMIN})
    return SecurityContext(
        principal=AuthenticatedPrincipal(
            subject="admin-sub",
            principal_type=PrincipalType.USER,
            external_tenant_id=TENANT,
            authentication_mode=AuthenticationMode.TEST,
        ),
        tenant_id=TENANT,
        roles=roles,
        permissions=permissions_for_roles(roles),
        correlation_id="corr-audit",
        authentication_mode=AuthenticationMode.TEST,
        principal_id="admin-sub",
    )


# -- redaction ---------------------------------------------------------------
def test_hash_identifier_is_stable_and_nonreversible():
    assert hash_identifier("novabank-admin-sub") == hash_identifier("novabank-admin-sub")
    assert hash_identifier("novabank-admin-sub") != "novabank-admin-sub"
    assert hash_identifier(None) is None
    assert hash_identifier("  ") is None


def test_sanitize_metadata_drops_secret_keys_and_values():
    dirty = {
        "role": "tenant_admin",
        "authorization": "Bearer eyJabc.def.ghi",
        "api_key": "supersecret",
        "note": "Bearer eyJraw.tok.en",
    }
    clean = sanitize_metadata(dirty)
    assert clean["role"] == "tenant_admin"
    assert "authorization" not in clean
    assert "api_key" not in clean
    assert clean["note"] == "[redacted]"


def test_contains_secret_detects_nested_secrets():
    assert contains_secret({"outer": {"token": "abc"}})
    assert contains_secret(["Bearer eyJa.b.c"])
    assert not contains_secret({"role": "executive_reader"})


def test_metadata_is_bounded():
    dirty = {f"k{i}": "v" for i in range(100)}
    assert len(sanitize_metadata(dirty)) <= 20


# -- append-only behaviour ---------------------------------------------------
def test_denial_event_is_persisted(uow):
    audit = SecurityAuditService(uow)
    audit.record_authorization_denied(
        _context(), action="api.predictions.promote", resource_type="api_route"
    )
    audit.commit()
    page = uow.security_audit_events.page(TENANT, limit=10)
    assert len(page.items) == 1
    assert page.items[0].decision == "deny"


def test_authentication_failure_has_no_tenant(uow):
    audit = SecurityAuditService(uow)
    audit.record_authentication_failure(
        category=AuthenticationFailureCategory.EXPIRED, correlation_id="c"
    )
    audit.commit()
    # tenant_id is None, so it is not returned by a tenant-scoped page query.
    page = uow.security_audit_events.page(TENANT, limit=10)
    assert page.items == []


def test_sensitive_action_records_redacted_metadata(uow):
    audit = SecurityAuditService(uow)
    audit.record_sensitive_action(
        _context(),
        action=SecurityAuditAction.ROLE_ASSIGNMENT_CREATED,
        permission=Permission.SECURITY_ROLES_MANAGE,
        resource_type="role_assignment",
        resource_id="rol_1",
        metadata={"role": "executive_reader", "token": "eyJa.b.c"},
    )
    audit.commit()
    page = uow.security_audit_events.page(TENANT, limit=10)
    event = page.items[0]
    assert event.decision == "allow"
    assert "token" not in event.event_metadata
    assert event.resource_id_hash == hash_identifier("rol_1")


def test_pagination_is_bounded_and_ordered(uow):
    audit = SecurityAuditService(uow)
    for i in range(5):
        audit.record_authorization_denied(
            _context(), action=f"api.op{i}", resource_type="api_route"
        )
    audit.commit()
    first = uow.security_audit_events.page(TENANT, limit=2)
    assert len(first.items) == 2
    assert first.next_cursor is not None
    # sequence_no strictly decreasing (stable ordering).
    seqs = [item.sequence_no for item in first.items]
    assert seqs == sorted(seqs, reverse=True)
    second = uow.security_audit_events.page(TENANT, limit=2, cursor=first.next_cursor)
    assert all(item.sequence_no < first.next_cursor for item in second.items)


def test_limit_is_capped(uow):
    page = uow.security_audit_events.page(TENANT, limit=10_000)
    assert page.limit <= 100


# -- fail-closed audit-write policy ------------------------------------------
class _BrokenAuditRepo:
    def append(self, **_kwargs):
        raise RuntimeError("audit backend down")


def test_failclosed_audit_write_failure_raises(uow):
    uow.security_audit_events = _BrokenAuditRepo()  # type: ignore[assignment]
    audit = SecurityAuditService(uow)
    with pytest.raises(AuditWriteError):
        audit.record_sensitive_action(
            _context(),
            action=SecurityAuditAction.ROLE_ASSIGNMENT_CREATED,
            permission=Permission.SECURITY_ROLES_MANAGE,
            resource_type="role_assignment",
        )


def test_besteffort_audit_write_failure_is_swallowed(uow):
    uow.security_audit_events = _BrokenAuditRepo()  # type: ignore[assignment]
    audit = SecurityAuditService(uow)
    # A non-fail-closed permission logs and returns None instead of raising.
    result = audit.record_sensitive_action(
        _context(),
        action=SecurityAuditAction.SCENARIO_EXECUTED,
        permission=Permission.SCENARIOS_RUN,
        resource_type="scenario",
    )
    assert result is None
