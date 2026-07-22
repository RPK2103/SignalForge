"""Versioned readiness intelligence API routes."""

from fastapi import APIRouter, Depends

from app.api.dependencies import require_json_content_type
from app.core.openapi import JSON_BODY_ERROR_RESPONSES
from app.repositories import get_catalog_repository
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.api_v2 import ReadinessAssessRequest, ReadinessAssessResponse
from app.services.readiness_orchestrator import ReadinessOrchestrator

router = APIRouter(prefix="/readiness", tags=["Readiness Intelligence"])


def _get_orchestrator(
    catalog: CatalogRepository = Depends(get_catalog_repository),
) -> ReadinessOrchestrator:
    return ReadinessOrchestrator(catalog=catalog)


@router.post(
    "/assess",
    response_model=ReadinessAssessResponse,
    responses=JSON_BODY_ERROR_RESPONSES,
    dependencies=[Depends(require_json_content_type)],
)
def assess_readiness(
    request: ReadinessAssessRequest,
    orchestrator: ReadinessOrchestrator = Depends(_get_orchestrator),
) -> ReadinessAssessResponse:
    return orchestrator.assess(request)
