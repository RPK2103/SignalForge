"""Dependency injection for the v3 enterprise API (Phase 3 Prompt 7).

Security flow per request:
1. ``AuthenticationMiddleware`` verifies the bearer principal and stashes it on
   ``request.state`` (no anonymous access to ``/api/v3``).
2. ``get_security_context`` selects the tenant (``X-SignalForge-Tenant-ID`` header
   or an unambiguous token claim), resolves the principal's active roles and
   effective permissions, and sets the transaction-local PostgreSQL RLS tenant
   context.
3. ``require_permission`` enforces the route's permission (deny-by-default).

The tenant header is a *selector* only — it never grants membership. Foreign and
nonexistent tenants are externally indistinguishable (404). A missing tenant
selector preserves the legacy 400 (tenant context required).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.persistence_dependencies import get_db_session
from app.db.unit_of_work import UnitOfWork
from app.domain.tenant_context import (
    InvalidTenantContextError,
    TenantContext,
    normalize_tenant_id,
)
from app.security.audit import SecurityAuditService
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.context_resolver import SecurityContextResolver
from app.security.enums import AuthenticationFailureCategory, Permission
from app.security.exceptions import AuthenticationError
from app.security.principal import AuthenticatedPrincipal
from app.security.rls import set_transaction_tenant
from app.services.enterprise.enterprise_services import (
    DeliveryService,
    EnterpriseCatalogService,
    EnterpriseHierarchyService,
    EnterpriseProfileService,
    IngestionService,
    InitiativeProjectService,
    RelationshipService,
)
from app.services.enterprise.exceptions import TenantContextError
from app.services.enterprise.legacy_compat_service import LegacyCompatibilityService

TENANT_HEADER = "X-SignalForge-Tenant-ID"


def get_correlation_id(request: Request) -> str:
    existing = getattr(request.state, "correlation_id", None)
    if existing:
        return str(existing)
    return uuid.uuid4().hex


def _require_principal(request: Request) -> AuthenticatedPrincipal:
    principal = getattr(request.state, "auth_principal", None)
    if principal is None:
        # Reached only if the authentication middleware was bypassed.
        raise AuthenticationError(category=AuthenticationFailureCategory.MISSING_TOKEN)
    return principal


def get_security_context(
    request: Request,
    session: Session = Depends(get_db_session),
    tenant_header: Annotated[str | None, Header(alias=TENANT_HEADER)] = None,
) -> SecurityContext:
    principal = _require_principal(request)
    correlation_id = get_correlation_id(request)

    selector = tenant_header if (tenant_header and tenant_header.strip()) else None
    if selector is None:
        selector = principal.claimed_tenant_selector
    if selector is None:
        raise TenantContextError(f"Missing required tenant header '{TENANT_HEADER}'")

    try:
        normalized = normalize_tenant_id(selector)
    except InvalidTenantContextError as exc:
        raise TenantContextError(f"Invalid tenant context: {exc}") from exc

    # Set RLS context first so the resolver can read tenant-scoped principal rows
    # under forced row-level security in PostgreSQL.
    set_transaction_tenant(session, normalized)

    resolver = SecurityContextResolver(UnitOfWork(session))
    return resolver.resolve(principal, requested_tenant=normalized, correlation_id=correlation_id)


SecurityContextDep = Annotated[SecurityContext, Depends(get_security_context)]


def get_authorization_service() -> AuthorizationService:
    return AuthorizationService()


def get_audit_service(session: Session = Depends(get_db_session)) -> SecurityAuditService:
    return SecurityAuditService(UnitOfWork(session))


def require_permission(permission: Permission) -> Callable[..., SecurityContext]:
    """Route dependency factory enforcing one permission (deny-by-default)."""

    def _dependency(
        context: SecurityContext = Depends(get_security_context),
        authz: AuthorizationService = Depends(get_authorization_service),
        audit: SecurityAuditService = Depends(get_audit_service),
    ) -> SecurityContext:
        outcome = authz.check(context, permission, context.tenant_id)
        if not outcome.allowed:
            audit.record_authorization_denied(
                context,
                action=f"api.{permission.value}",
                resource_type="api_route",
                reason_code=outcome.reason_code,
            )
            audit.commit()  # persist the denial before failing closed
            authz.require(context, permission, context.tenant_id)
        return context

    # Tag the closure so the permission-coverage audit can introspect which
    # permission each route enforces (see app.security.coverage).
    _dependency.__signalforge_required_permission__ = permission  # type: ignore[attr-defined]
    return _dependency


def get_tenant_context(
    context: SecurityContext = Depends(get_security_context),
) -> TenantContext:
    return TenantContext(context.tenant_id)


def get_unit_of_work(session: Session = Depends(get_db_session)) -> UnitOfWork:
    return UnitOfWork(session)


def get_hierarchy_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> EnterpriseHierarchyService:
    return EnterpriseHierarchyService(uow)


def get_profile_service(uow: UnitOfWork = Depends(get_unit_of_work)) -> EnterpriseProfileService:
    return EnterpriseProfileService(uow)


def get_catalog_service(uow: UnitOfWork = Depends(get_unit_of_work)) -> EnterpriseCatalogService:
    return EnterpriseCatalogService(uow)


def get_initiative_project_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> InitiativeProjectService:
    return InitiativeProjectService(uow)


def get_delivery_service(uow: UnitOfWork = Depends(get_unit_of_work)) -> DeliveryService:
    return DeliveryService(uow)


def get_relationship_service(uow: UnitOfWork = Depends(get_unit_of_work)) -> RelationshipService:
    return RelationshipService(uow)


def get_ingestion_service(uow: UnitOfWork = Depends(get_unit_of_work)) -> IngestionService:
    return IngestionService(uow)


def get_legacy_service(uow: UnitOfWork = Depends(get_unit_of_work)) -> LegacyCompatibilityService:
    return LegacyCompatibilityService(uow)


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]
