"""Security administration + audit v3 routes (Phase 3 Prompt 7).

Authorization is enforced at the service layer; these routes only marshal input
and output. Access is restricted to security auditors / tenant admins.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.persistence_dependencies import get_db_session
from app.api.v3.dependencies import SecurityContextDep
from app.db.unit_of_work import UnitOfWork
from app.security.administration import SecurityAdministrationService
from app.security.enums import PrincipalType, SecurityRole
from app.security.models import (
    AuditPage,
    IdentityProviderRecord,
    RoleAssignmentRecord,
    SecurityPrincipalRecord,
)

router = APIRouter(prefix="/api/v3/security", tags=["Enterprise Security"])


def get_admin_service(
    session: Session = Depends(get_db_session),
) -> SecurityAdministrationService:
    return SecurityAdministrationService(UnitOfWork(session))


class CreatePrincipalRequest(BaseModel):
    principal_type: PrincipalType
    external_subject_id: str = Field(min_length=1, max_length=255)
    external_application_id: str | None = Field(default=None, max_length=255)
    display_label: str | None = Field(default=None, max_length=120)


class AssignRoleRequest(BaseModel):
    principal_id: str = Field(min_length=1, max_length=64)
    role: SecurityRole
    reason: str | None = Field(default=None, max_length=500)


class UpsertIdentityProviderRequest(BaseModel):
    provider_type: str = Field(pattern="^(entra_oidc|local_development|test)$")
    external_tenant_id: str = Field(min_length=1, max_length=128)
    issuer: str = Field(min_length=1, max_length=512)
    audience: str = Field(min_length=1, max_length=512)
    enabled: bool = True
    metadata: dict | None = None


@router.get("/audit-events", response_model=AuditPage)
def list_audit_events(
    context: SecurityContextDep,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None, max_length=64),
    service: SecurityAdministrationService = Depends(get_admin_service),
) -> AuditPage:
    return service.read_audit(context, limit=limit, cursor=cursor, action=action)


@router.post("/principals", response_model=SecurityPrincipalRecord, status_code=201)
def create_principal(
    request: CreatePrincipalRequest,
    context: SecurityContextDep,
    service: SecurityAdministrationService = Depends(get_admin_service),
) -> SecurityPrincipalRecord:
    return service.create_principal(
        context,
        principal_type=request.principal_type,
        external_subject_id=request.external_subject_id,
        external_application_id=request.external_application_id,
        display_label=request.display_label,
    )


@router.post("/role-assignments", response_model=RoleAssignmentRecord, status_code=201)
def assign_role(
    request: AssignRoleRequest,
    context: SecurityContextDep,
    service: SecurityAdministrationService = Depends(get_admin_service),
) -> RoleAssignmentRecord:
    return service.assign_role(
        context,
        principal_id=request.principal_id,
        role=request.role,
        reason=request.reason,
    )


@router.delete("/role-assignments/{assignment_id}", response_model=RoleAssignmentRecord)
def revoke_role(
    assignment_id: Annotated[str, Field(max_length=64)],
    context: SecurityContextDep,
    service: SecurityAdministrationService = Depends(get_admin_service),
) -> RoleAssignmentRecord:
    return service.revoke_role(context, assignment_id=assignment_id)


@router.get("/identity-providers", response_model=list[IdentityProviderRecord])
def list_identity_providers(
    context: SecurityContextDep,
    service: SecurityAdministrationService = Depends(get_admin_service),
) -> list[IdentityProviderRecord]:
    return service.list_identity_providers(context)


@router.put("/identity-providers", response_model=IdentityProviderRecord)
def upsert_identity_provider(
    request: UpsertIdentityProviderRequest,
    context: SecurityContextDep,
    service: SecurityAdministrationService = Depends(get_admin_service),
) -> IdentityProviderRecord:
    return service.upsert_identity_provider(
        context,
        provider_type=request.provider_type,
        external_tenant_id=request.external_tenant_id,
        issuer=request.issuer,
        audience=request.audience,
        enabled=request.enabled,
        metadata=request.metadata,
    )
