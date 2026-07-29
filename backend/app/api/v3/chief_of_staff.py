"""AI Chief of Staff v3 read-only APIs (Phase 3 Prompt 6).

Read-only endpoints. Generation and review mutations remain CLI/service-only
because the tenant header is development context, not authentication.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v3.dependencies import TenantContextDep, get_unit_of_work
from app.db.unit_of_work import UnitOfWork
from app.domain.chief_of_staff_models import (
    ChiefOfStaffBriefRecord,
    ChiefOfStaffCitation,
    ChiefOfStaffClaim,
    ChiefOfStaffRunRecord,
    QualitySummary,
)
from app.domain.enterprise_models import Page
from app.services.chief_of_staff.service import ChiefOfStaffService

router = APIRouter(prefix="/api/v3/chief-of-staff", tags=["AI Chief of Staff"])

_PAGE = Query(default=20, ge=1, le=100)
_OFFSET = Query(default=0, ge=0)


def _service(uow: UnitOfWork = Depends(get_unit_of_work)) -> ChiefOfStaffService:
    return ChiefOfStaffService(uow)


@router.get(
    "/briefs",
    response_model=Page[ChiefOfStaffBriefRecord],
    summary="List Chief of Staff briefs",
    responses={
        200: {
            "description": "Paginated briefs",
            "content": {
                "application/json": {
                    "example": {
                        "items": [],
                        "total": 0,
                        "limit": 20,
                        "offset": 0,
                    }
                }
            },
        }
    },
)
def list_briefs(
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    intent: str | None = Query(default=None),
) -> Page[ChiefOfStaffBriefRecord]:
    return uow.cos_briefs.list(
        ctx,
        limit=limit,
        offset=offset,
        target_type=target_type,
        target_id=target_id,
        intent=intent,
    )


@router.get(
    "/briefs/{brief_id}",
    response_model=ChiefOfStaffBriefRecord,
    summary="Get one Chief of Staff brief",
)
def get_brief(
    brief_id: str,
    ctx: TenantContextDep,
    service: ChiefOfStaffService = Depends(_service),
) -> ChiefOfStaffBriefRecord:
    return service.get_brief(ctx, brief_id)


@router.get(
    "/briefs/{brief_id}/claims",
    response_model=list[ChiefOfStaffClaim],
    summary="List claims for a brief (stable ordering)",
)
def list_claims(
    brief_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> list[ChiefOfStaffClaim]:
    return uow.cos_briefs.list_claims(ctx, brief_id)


@router.get(
    "/briefs/{brief_id}/citations",
    response_model=list[ChiefOfStaffCitation],
    summary="List citations for a brief (stable ordering)",
)
def list_citations(
    brief_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> list[ChiefOfStaffCitation]:
    return uow.cos_briefs.list_citations(ctx, brief_id)


@router.get(
    "/briefs/{brief_id}/evidence-summary",
    summary="Bounded evidence summary without raw package payload",
)
def evidence_summary(
    brief_id: str,
    ctx: TenantContextDep,
    service: ChiefOfStaffService = Depends(_service),
) -> dict:
    return service.evidence_summary(ctx, brief_id)


@router.get(
    "/runs",
    response_model=Page[ChiefOfStaffRunRecord],
    summary="List Chief of Staff generation runs",
)
def list_runs(
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    intent: str | None = Query(default=None),
    generation_state: str | None = Query(default=None),
) -> Page[ChiefOfStaffRunRecord]:
    return uow.cos_runs.list(
        ctx,
        limit=limit,
        offset=offset,
        target_type=target_type,
        target_id=target_id,
        intent=intent,
        generation_state=generation_state,
    )


@router.get(
    "/quality-summary",
    response_model=QualitySummary,
    summary="Bounded Chief of Staff quality summary",
)
def quality_summary(
    ctx: TenantContextDep,
    service: ChiefOfStaffService = Depends(_service),
) -> QualitySummary:
    return service.quality_summary(ctx)
