"""Version 2 API router — production readiness intelligence surface.

Every route below is authenticated (default-deny middleware) and explicitly
RBAC-gated. Single-permission routers are gated here at include time; routers
with per-route permissions (assessments, simulation-records) declare them on
each route. See ``architecture/phase-3-enterprise-security-scale.md`` for the
full route-permission table.
"""

from fastapi import APIRouter, Depends

from app.api.v2 import (
    assessments,
    capabilities,
    catalog,
    readiness,
    simulation_records,
    simulations,
)
from app.api.v3.dependencies import require_permission
from app.security.enums import Permission

router = APIRouter(prefix="/api/v2")
router.include_router(
    readiness.router,
    dependencies=[Depends(require_permission(Permission.ENTERPRISE_READ))],
)
router.include_router(
    simulations.router,
    dependencies=[Depends(require_permission(Permission.SCENARIOS_RUN))],
)
router.include_router(assessments.router)
router.include_router(simulation_records.router)
router.include_router(
    capabilities.router,
    dependencies=[Depends(require_permission(Permission.ENTERPRISE_READ))],
)
router.include_router(
    catalog.router,
    dependencies=[Depends(require_permission(Permission.ENTERPRISE_READ))],
)
