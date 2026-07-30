"""Signed short-lived development/test token issuance (Prompt 7).

Used by the security CLI (``local_development`` mode) and by tests. There is NO
public API endpoint that issues these tokens, and production rejects the modes
that accept them.
"""

from __future__ import annotations

import time

import jwt

from app.security.enums import PrincipalType

_ALGORITHM = "HS256"


def issue_symmetric_token(
    *,
    secret: str,
    issuer: str,
    audience: str,
    subject: str,
    external_tenant_id: str,
    roles: list[str] | tuple[str, ...] = (),
    tenant_memberships: list[str] | tuple[str, ...] | None = None,
    tenant_selector: str | None = None,
    principal_type: PrincipalType = PrincipalType.USER,
    application_id: str | None = None,
    display_label: str | None = None,
    ttl_seconds: int = 3600,
    not_before_offset_seconds: int = 0,
    issued_now: int | None = None,
) -> str:
    """Mint a bounded-lifetime HS256 token carrying explicit tenant + role claims."""
    if not secret:
        raise ValueError("A signing secret is required to issue a development token")
    now = int(issued_now if issued_now is not None else time.time())
    memberships = list(tenant_memberships) if tenant_memberships else [external_tenant_id]
    payload: dict[str, object] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "tid": external_tenant_id,
        "ptyp": principal_type.value,
        "roles": list(roles),
        "tenants": memberships,
        "iat": now,
        "nbf": now + not_before_offset_seconds,
        "exp": now + ttl_seconds,
    }
    if tenant_selector:
        payload["tenant"] = tenant_selector
    if application_id:
        payload["appid"] = application_id
    if display_label:
        payload["name"] = display_label
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)
