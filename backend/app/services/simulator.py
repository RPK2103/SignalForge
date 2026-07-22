from app.adapters.legacy_simulation_adapter import (
    LegacySimulationAdapter,
    _build_simulation_summary,
    _recommended_team,
)
from app.repositories.mock_catalog_repository import MockCatalogRepository
from app.schemas.simulator import SimulateRequest, SimulateResponse

_catalog = MockCatalogRepository()
_adapter = LegacySimulationAdapter(_catalog)


def simulate_staffing(request: SimulateRequest) -> SimulateResponse:
    return _adapter.simulate(request)


__all__ = [
    "_build_simulation_summary",
    "_recommended_team",
    "simulate_staffing",
]
