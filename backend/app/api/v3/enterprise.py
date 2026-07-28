"""Enterprise data-foundation v3 routes.

Read-oriented and case-oriented endpoints only (no unrestricted bulk-write CRUD).
Every route requires tenant context; tenant-qualified absence returns 404 without
revealing cross-tenant existence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.api.v3.dependencies import (
    TenantContextDep,
    get_catalog_service,
    get_delivery_service,
    get_hierarchy_service,
    get_ingestion_service,
    get_initiative_project_service,
    get_legacy_service,
    get_profile_service,
    get_unit_of_work,
)
from app.api.v3.schemas import (
    AppendEvidenceRequest,
    CompleteIngestionRunRequest,
    DemoTenantSummary,
    EvidenceAppendResponse,
    RegisterDataSourceRequest,
    StartIngestionRunRequest,
)
from app.db.models import enterprise as orm
from app.db.unit_of_work import UnitOfWork
from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import EnterpriseEntityType
from app.services.enterprise.enterprise_services import (
    DeliveryService,
    EnterpriseCatalogService,
    EnterpriseHierarchyService,
    EnterpriseProfileService,
    IngestionService,
    InitiativeProjectService,
)
from app.services.enterprise.legacy_compat_service import (
    LegacyCatalogProjection,
    LegacyCompatibilityService,
)

router = APIRouter(prefix="/api/v3", tags=["Enterprise Data Foundation"])

_PAGE = Query(default=20, ge=1, le=100)
_OFFSET = Query(default=0, ge=0)

_COUNT_MODELS = {
    "organizations": orm.Organization,
    "business_units": orm.BusinessUnit,
    "departments": orm.Department,
    "teams": orm.Team,
    "engineer_profiles": orm.EngineerProfile,
    "capabilities": orm.EnterpriseCapability,
    "skills": orm.EnterpriseSkill,
    "initiatives": orm.Initiative,
    "projects": orm.EnterpriseProject,
    "repositories": orm.Repository,
    "sprints": orm.Sprint,
    "work_items": orm.WorkItem,
    "incidents": orm.Incident,
    "deployments": orm.Deployment,
    "dependencies": orm.Dependency,
    "ownership": orm.Ownership,
    "availability": orm.Availability,
    "data_sources": orm.DataSource,
    "ingestion_runs": orm.IngestionRun,
    "evidence_signals": orm.EvidenceSignal,
}


# ---------------------------------------------------------------------------
# Organization hierarchy (read)
# ---------------------------------------------------------------------------
@router.get("/organization", response_model=dm.Organization)
def get_organization(
    ctx: TenantContextDep,
    service: EnterpriseHierarchyService = Depends(get_hierarchy_service),
) -> dm.Organization:
    return service.get_tenant_organization(ctx)


@router.get("/business-units", response_model=dm.Page[dm.BusinessUnit])
def list_business_units(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: EnterpriseHierarchyService = Depends(get_hierarchy_service),
) -> dm.Page[dm.BusinessUnit]:
    return service.list_business_units(ctx, limit=limit, offset=offset)


@router.get("/departments", response_model=dm.Page[dm.Department])
def list_departments(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: EnterpriseHierarchyService = Depends(get_hierarchy_service),
) -> dm.Page[dm.Department]:
    return service.list_departments(ctx, limit=limit, offset=offset)


@router.get("/teams", response_model=dm.Page[dm.Team])
def list_teams(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: EnterpriseHierarchyService = Depends(get_hierarchy_service),
) -> dm.Page[dm.Team]:
    return service.list_teams(ctx, limit=limit, offset=offset)


@router.get("/engineer-profiles", response_model=dm.Page[dm.EngineerProfile])
def list_engineer_profiles(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: EnterpriseProfileService = Depends(get_profile_service),
) -> dm.Page[dm.EngineerProfile]:
    return service.list_profiles(ctx, limit=limit, offset=offset)


@router.get("/engineer-profiles/{engineer_profile_id}", response_model=dm.EngineerProfile)
def get_engineer_profile(
    engineer_profile_id: str,
    ctx: TenantContextDep,
    service: EnterpriseProfileService = Depends(get_profile_service),
) -> dm.EngineerProfile:
    return service.get_profile(ctx, engineer_profile_id)


@router.get("/capabilities", response_model=dm.Page[dm.EnterpriseCapability])
def list_capabilities(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: EnterpriseCatalogService = Depends(get_catalog_service),
) -> dm.Page[dm.EnterpriseCapability]:
    return service.list_capabilities(ctx, limit=limit, offset=offset)


@router.get("/initiatives", response_model=dm.Page[dm.Initiative])
def list_initiatives(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: InitiativeProjectService = Depends(get_initiative_project_service),
) -> dm.Page[dm.Initiative]:
    return service.list_initiatives(ctx, limit=limit, offset=offset)


@router.get("/projects", response_model=dm.Page[dm.EnterpriseProject])
def list_projects(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: InitiativeProjectService = Depends(get_initiative_project_service),
) -> dm.Page[dm.EnterpriseProject]:
    return service.list_projects(ctx, limit=limit, offset=offset)


@router.get("/repositories", response_model=dm.Page[dm.Repository])
def list_repositories(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: DeliveryService = Depends(get_delivery_service),
) -> dm.Page[dm.Repository]:
    return service.list_repositories(ctx, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Provenance (read + case-oriented write)
# ---------------------------------------------------------------------------
@router.get("/data-sources", response_model=dm.Page[dm.DataSource])
def list_data_sources(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: IngestionService = Depends(get_ingestion_service),
) -> dm.Page[dm.DataSource]:
    return service.list_data_sources(ctx, limit=limit, offset=offset)


@router.post("/data-sources", response_model=dm.DataSource, status_code=status.HTTP_201_CREATED)
def register_data_source(
    request: RegisterDataSourceRequest,
    ctx: TenantContextDep,
    service: IngestionService = Depends(get_ingestion_service),
) -> dm.DataSource:
    return service.register_data_source(
        ctx,
        source_type=request.source_type,
        display_name=request.display_name,
        credential_reference=request.credential_reference,
        config_reference=request.config_reference,
        permission_classification=request.permission_classification,
    )


@router.get("/ingestion-runs", response_model=dm.Page[dm.IngestionRun])
def list_ingestion_runs(
    ctx: TenantContextDep,
    data_source_id: str | None = Query(default=None),
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: IngestionService = Depends(get_ingestion_service),
) -> dm.Page[dm.IngestionRun]:
    return service.list_runs(ctx, data_source_id=data_source_id, limit=limit, offset=offset)


@router.post("/ingestion-runs", response_model=dm.IngestionRun, status_code=status.HTTP_201_CREATED)
def start_ingestion_run(
    request: StartIngestionRunRequest,
    ctx: TenantContextDep,
    service: IngestionService = Depends(get_ingestion_service),
) -> dm.IngestionRun:
    return service.start_run(
        ctx,
        data_source_id=request.data_source_id,
        run_type=request.run_type,
        run_key=request.run_key,
    )


@router.post("/ingestion-runs/{ingestion_run_id}/complete", response_model=dm.IngestionRun)
def complete_ingestion_run(
    ingestion_run_id: str,
    request: CompleteIngestionRunRequest,
    ctx: TenantContextDep,
    service: IngestionService = Depends(get_ingestion_service),
) -> dm.IngestionRun:
    return service.complete_run(
        ctx,
        ingestion_run_id=ingestion_run_id,
        status=request.status,
        records_read=request.records_read,
        records_written=request.records_written,
        records_skipped=request.records_skipped,
        error_category=request.error_category,
        error_summary=request.error_summary,
    )


@router.get("/evidence-signals", response_model=dm.Page[dm.EvidenceSignal])
def list_evidence_signals(
    ctx: TenantContextDep,
    subject_type: EnterpriseEntityType = Query(...),
    subject_id: str = Query(..., min_length=1, max_length=128),
    limit: int = _PAGE,
    offset: int = _OFFSET,
    service: IngestionService = Depends(get_ingestion_service),
) -> dm.Page[dm.EvidenceSignal]:
    return service.list_evidence_by_subject(
        ctx, subject_type=subject_type, subject_id=subject_id, limit=limit, offset=offset
    )


@router.post("/evidence-signals", response_model=EvidenceAppendResponse)
def append_evidence(
    request: AppendEvidenceRequest,
    ctx: TenantContextDep,
    service: IngestionService = Depends(get_ingestion_service),
) -> EvidenceAppendResponse:
    signal, created = service.append_evidence(
        ctx,
        data_source_id=request.data_source_id,
        source_record_id=request.source_record_id,
        signal_type=request.signal_type,
        subject_type=request.subject_type,
        subject_id=request.subject_id,
        payload=request.payload,
        event_time=request.event_time,
        observed_at=request.observed_at,
        ingestion_run_id=request.ingestion_run_id,
        confidence=request.confidence,
        permission_classification=request.permission_classification,
    )
    return EvidenceAppendResponse(created=created, signal=signal)


# ---------------------------------------------------------------------------
# Demo summary + Phase 2 compatibility projection
# ---------------------------------------------------------------------------
@router.get("/demo/summary", response_model=DemoTenantSummary)
def demo_summary(
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> DemoTenantSummary:
    counts: dict[str, int] = {}
    for key, model in _COUNT_MODELS.items():
        counts[key] = (
            uow.session.scalar(
                select(func.count()).select_from(model).where(model.tenant_id == ctx.tenant_id)
            )
            or 0
        )
    org = uow.organizations.get_tenant_organization(ctx)
    return DemoTenantSummary(
        tenant_id=ctx.tenant_id,
        organization_id=org.organization_id if org else None,
        counts=counts,
    )


@router.get("/legacy-projection", response_model=LegacyCatalogProjection)
def legacy_projection(
    ctx: TenantContextDep,
    service: LegacyCompatibilityService = Depends(get_legacy_service),
) -> LegacyCatalogProjection:
    return service.project_catalog(ctx)
