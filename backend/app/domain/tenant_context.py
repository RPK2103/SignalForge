"""Explicit tenant-context abstraction (Phase 3 Prompt 1).

Tenant access must never depend on a caller remembering to add an ad-hoc query
filter. Instead, an immutable ``TenantContext`` is threaded through every service
and repository boundary. Repositories require it and scope all reads, writes,
updates and relationship resolution to ``context.tenant_id``.

NOTE: This is a *data-boundary* mechanism only. It is NOT authentication or
authorization. Enterprise identity (Entra ID), RBAC and PostgreSQL row-level
security are deliberately deferred to Phase 3 Prompt 7.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TENANT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")

# Deterministic tenant identifiers used by migrations and seeds. The legacy
# tenant is a compatibility bucket for pre-Phase-3 catalog rows; NovaBank is the
# fictional demo tenant introduced in Phase 3 Prompt 1.
LEGACY_TENANT_ID = "legacy-default"
NOVABANK_TENANT_ID = "novabank"


class InvalidTenantContextError(ValueError):
    """Raised when a tenant identifier is missing or malformed."""


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable security-boundary carrier for a single tenant.

    ``tenant_id`` is the security boundary. It is a stable, deterministic,
    lowercase slug (never LLM-generated).
    """

    tenant_id: str

    def __post_init__(self) -> None:
        normalized = normalize_tenant_id(self.tenant_id)
        # dataclass is frozen; use object.__setattr__ to store the normalized form.
        object.__setattr__(self, "tenant_id", normalized)

    @classmethod
    def require(cls, tenant_id: str | None) -> TenantContext:
        """Build a context, rejecting missing/blank identifiers."""
        if tenant_id is None or not str(tenant_id).strip():
            raise InvalidTenantContextError("Tenant context is required")
        return cls(tenant_id=str(tenant_id))


def normalize_tenant_id(tenant_id: str) -> str:
    value = (tenant_id or "").strip().lower()
    if not value:
        raise InvalidTenantContextError("Tenant identifier must not be empty")
    if len(value) > 64:
        raise InvalidTenantContextError("Tenant identifier must be at most 64 characters")
    if not _TENANT_ID_PATTERN.match(value):
        raise InvalidTenantContextError(
            "Tenant identifier must be a lowercase slug (a-z, 0-9, hyphen)"
        )
    return value
