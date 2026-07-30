"""Test-only signed JWT helpers (Phase 3 Prompt 7).

These mint tokens for the in-process ``test`` authentication mode ONLY. The test
issuer/audience/secret are isolated from local-development and Entra, and the
mode cannot run in production (enforced by ``AuthenticationService``).
"""

from __future__ import annotations

from app.security.authentication import TEST_AUDIENCE, TEST_ISSUER, TEST_SECRET
from app.security.dev_tokens import issue_symmetric_token
from app.security.enums import PrincipalType


def mint_test_token(
    *,
    subject: str = "test-user",
    external_tenant_id: str = "novabank",
    roles: tuple[str, ...] = ("tenant_admin",),
    tenant_memberships: tuple[str, ...] = ("*",),
    tenant_selector: str | None = None,
    principal_type: PrincipalType = PrincipalType.USER,
    application_id: str | None = None,
    ttl_seconds: int = 86_400,
    not_before_offset_seconds: int = 0,
    issued_now: int | None = None,
) -> str:
    return issue_symmetric_token(
        secret=TEST_SECRET,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        subject=subject,
        external_tenant_id=external_tenant_id,
        roles=list(roles),
        tenant_memberships=list(tenant_memberships),
        tenant_selector=tenant_selector,
        principal_type=principal_type,
        application_id=application_id,
        ttl_seconds=ttl_seconds,
        not_before_offset_seconds=not_before_offset_seconds,
        issued_now=issued_now,
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# A broad principal (tenant_admin, member of every tenant) used by the pre-Prompt-7
# regression suites so their existing tenant-selection/permission expectations
# continue to hold under mandatory authentication.
BROAD_TEST_TOKEN = mint_test_token(subject="regression-admin")


def broad_test_headers() -> dict[str, str]:
    return dict(bearer(BROAD_TEST_TOKEN))


# The tenant selector header used by suites that exercise now-RBAC-gated
# ``/api/v2`` and legacy root routes. The broad principal is a wildcard member,
# so the selector resolves to a concrete tenant for authorization.
TENANT_HEADER = "X-SignalForge-Tenant-ID"
DEFAULT_TEST_TENANT = "novabank"


def broad_tenant_headers(tenant: str = DEFAULT_TEST_TENANT) -> dict[str, str]:
    headers = dict(bearer(BROAD_TEST_TOKEN))
    headers[TENANT_HEADER] = tenant
    return headers
