from fastapi import APIRouter

from app.schemas.simulator import SimulateRequest, SimulateResponse
from app.services.simulator import simulate_staffing

router = APIRouter()


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    summary="Simulate removing engineers from a project team",
    response_description="Recalculated coverage, risk, success probability, and executive summary.",
)
def simulate_endpoint(request: SimulateRequest) -> SimulateResponse:
    """Staffing simulator for what-if team changes.

    Example request::

        {
          "project_name": "Azure AI Migration",
          "remove_engineers": ["Kavi"]
        }
    """
    return simulate_staffing(request)
