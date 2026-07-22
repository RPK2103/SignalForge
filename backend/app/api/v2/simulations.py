"""Versioned team simulation API routes."""

from fastapi import APIRouter, Depends

from app.api.dependencies import require_json_content_type
from app.core.openapi import JSON_BODY_ERROR_RESPONSES
from app.repositories import get_catalog_repository
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.api_v2 import SimulationRequest, SimulationResponse
from app.services.simulation_orchestrator import SimulationOrchestrator

router = APIRouter(prefix="/simulations", tags=["Team Simulation"])


def _get_orchestrator(
    catalog: CatalogRepository = Depends(get_catalog_repository),
) -> SimulationOrchestrator:
    return SimulationOrchestrator(catalog=catalog)


@router.post(
    "",
    response_model=SimulationResponse,
    responses=JSON_BODY_ERROR_RESPONSES,
    dependencies=[Depends(require_json_content_type)],
    summary="Simulate a team composition change",
    description=(
        "Run a deterministic what-if simulation by applying add, remove, replace, "
        "or direct compare operations against a baseline team."
    ),
)
def simulate_team(
    request: SimulationRequest,
    orchestrator: SimulationOrchestrator = Depends(_get_orchestrator),
) -> SimulationResponse:
    return orchestrator.simulate(request)
