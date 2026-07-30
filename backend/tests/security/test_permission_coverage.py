"""Permission-coverage audit (Phase 3 Prompt 7 remediation).

Detects the broken-access-control class the independent audit flagged: a sensitive
permission that is defined in the RBAC matrix but never actually enforced by any
reachable code path. The registry in ``app.security.coverage`` is cross-checked
against LIVE route introspection and the application-service source — not string
comments — so a regression (e.g. dropping a route dependency) fails this test.
"""

from __future__ import annotations

import inspect

import pytest

from app.main import app
from app.security.administration import SecurityAdministrationService
from app.security.coverage import (
    SENSITIVE_PERMISSION_ENFORCEMENT,
    SENSITIVE_PERMISSIONS,
    EnforcementKind,
    route_enforced_permissions,
)
from app.security.enums import Permission


def test_every_sensitive_permission_is_classified():
    """No sensitive permission may be missing from (or extra in) the registry."""
    assert set(SENSITIVE_PERMISSION_ENFORCEMENT) == set(SENSITIVE_PERMISSIONS)


def test_route_classified_permissions_are_actually_enforced():
    """Each ROUTE-classified permission must be enforced by ≥1 live route."""
    enforced = route_enforced_permissions(app)
    for permission, record in SENSITIVE_PERMISSION_ENFORCEMENT.items():
        if record.kind is EnforcementKind.ROUTE:
            assert permission in enforced, (
                f"{permission.value} is classified ROUTE but no route enforces it"
            )
            assert enforced[permission], f"{permission.value} enforced by an empty route set"


def test_no_sensitive_route_permission_is_misclassified():
    """A sensitive permission enforced at a route must be classified ROUTE (drift guard)."""
    enforced = route_enforced_permissions(app)
    for permission in enforced:
        if permission in SENSITIVE_PERMISSIONS:
            record = SENSITIVE_PERMISSION_ENFORCEMENT[permission]
            assert record.kind is EnforcementKind.ROUTE, (
                f"{permission.value} is enforced by a route but classified {record.kind.value}"
            )


def test_service_classified_permissions_are_enforced_in_service_source():
    """Each SERVICE-classified permission must be referenced by the admin service."""
    source = inspect.getsource(SecurityAdministrationService)
    for permission, record in SENSITIVE_PERMISSION_ENFORCEMENT.items():
        if record.kind is EnforcementKind.SERVICE:
            assert permission.name in source, (
                f"{permission.value} is classified SERVICE but not referenced by "
                "SecurityAdministrationService"
            )


def test_deferred_permissions_have_no_reachable_route():
    """Deferred/CLI operations must not be silently reachable via an HTTP route."""
    enforced = route_enforced_permissions(app)
    for permission, record in SENSITIVE_PERMISSION_ENFORCEMENT.items():
        if record.kind in (EnforcementKind.DEFERRED, EnforcementKind.CLI):
            assert permission not in enforced, (
                f"{permission.value} is classified {record.kind.value} but a route enforces it; "
                "reclassify it as ROUTE"
            )


@pytest.mark.parametrize("permission", sorted(SENSITIVE_PERMISSIONS, key=lambda p: p.value))
def test_every_entry_is_documented(permission: Permission):
    """Every registry entry documents concrete enforcement sites."""
    record = SENSITIVE_PERMISSION_ENFORCEMENT[permission]
    assert record.sites, f"{permission.value} has no documented enforcement sites"
    if record.kind in (EnforcementKind.DEFERRED, EnforcementKind.CLI):
        assert record.note, f"{permission.value} ({record.kind.value}) must document a rationale"
