"""Read DTOs for the security domain (Phase 3 Prompt 7).

ORM rows never leave the repository layer; these bounded, secret-free models do.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IdentityProviderRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    provider_type: str
    external_tenant_id: str
    issuer: str
    audience: str
    enabled: bool
    configuration_version: int
    created_at: datetime
    updated_at: datetime


class SecurityPrincipalRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    principal_type: str
    external_subject_id: str
    external_application_id: str | None
    display_label: str | None
    status: str
    created_at: datetime
    deactivated_at: datetime | None


class RoleAssignmentRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    principal_id: str
    role: str
    valid_from: datetime
    valid_to: datetime | None
    assigned_by_principal_id: str | None
    reason: str | None
    created_at: datetime


class SecurityAuditEventRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence_no: int
    id: str
    tenant_id: str | None
    principal_id: str | None
    external_subject_hash: str | None
    action: str
    resource_type: str
    resource_id_hash: str | None
    decision: str
    reason_code: str
    correlation_id: str
    request_method: str | None
    request_path: str | None
    source_ip_hash: str | None
    event_metadata: dict
    created_at: datetime


class AuditPage(BaseModel):
    """Keyset-paginated audit history slice."""

    items: list[SecurityAuditEventRecord]
    next_cursor: int | None
    limit: int
