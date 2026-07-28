"""Dependency injection for the v3 enterprise API.

LOCAL DEVELOPMENT ONLY: tenant context is supplied through the
``X-SignalForge-Tenant-ID`` request header. This is a data-scoping mechanism to
exercise the tenant boundary — it is NOT authentication. Real enterprise identity
(Entra ID), RBAC and PostgreSQL RLS are deferred to Phase 3 Prompt 7.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.api.persistence_dependencies import get_db_session
from app.db.unit_of_work import UnitOfWork
from app.domain.tenant_context import InvalidTenantContextError, TenantContext
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


def get_tenant_context(
    tenant_header: Annotated[str | None, Header(alias=TENANT_HEADER)] = None,
) -> TenantContext:
    if tenant_header is None or not tenant_header.strip():
        raise TenantContextError(f"Missing required tenant header '{TENANT_HEADER}'")
    try:
        return TenantContext.require(tenant_header)
    except InvalidTenantContextError as exc:
        raise TenantContextError(f"Invalid tenant context: {exc}") from exc


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
