"""Persisted simulation history API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_json_content_type
from app.api.persistence_dependencies import get_simulation_persistence_service
from app.api.v3.dependencies import require_permission
from app.domain.persistence_models import PaginatedSimulationList, SimulationRecordResponse
from app.schemas.api_v2 import SimulationRequest
from app.security.context import SecurityContext
from app.security.enums import Permission
from app.services.persistence.exceptions import PersistenceError
from app.services.persistence.simulation_persistence_service import SimulationPersistenceService

router = APIRouter(prefix="/simulation-records", tags=["Simulation History"])


@router.post(
    "",
    response_model=SimulationRecordResponse,
    dependencies=[Depends(require_json_content_type)],
)
def create_simulation_record(
    request: SimulationRequest,
    context: SecurityContext = Depends(require_permission(Permission.SCENARIOS_RUN)),
    service: SimulationPersistenceService = Depends(get_simulation_persistence_service),
) -> SimulationRecordResponse:
    try:
        return service.create_simulation(context, request)
    except PersistenceError:
        raise


@router.get(
    "",
    response_model=PaginatedSimulationList,
    dependencies=[Depends(require_permission(Permission.SCENARIOS_READ))],
)
def list_simulation_records(
    project_id: str | None = Query(default=None),
    simulation_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: SimulationPersistenceService = Depends(get_simulation_persistence_service),
) -> PaginatedSimulationList:
    try:
        return service.list_simulations(
            project_id=project_id,
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
        )
    except PersistenceError:
        raise


@router.get(
    "/{simulation_record_id}",
    response_model=SimulationRecordResponse,
    dependencies=[Depends(require_permission(Permission.SCENARIOS_READ))],
)
def get_simulation_record(
    simulation_record_id: UUID,
    service: SimulationPersistenceService = Depends(get_simulation_persistence_service),
) -> SimulationRecordResponse:
    try:
        return service.get_simulation(simulation_record_id)
    except PersistenceError:
        raise
