"""Version 3 API router — enterprise + connectors + graph + prediction + scenarios + CoS.

Every subrouter is protected by authentication (middleware) plus a deny-by-default
baseline read permission enforced here. Sensitive operations additionally enforce
explicit permissions at the service layer.
"""

from fastapi import APIRouter, Depends

from app.api.v3 import (
    chief_of_staff,
    connectors,
    delivery_graph,
    enterprise,
    observability,
    predictions,
    scenarios,
    security,
)
from app.api.v3.dependencies import require_permission
from app.security.enums import Permission

router = APIRouter()
router.include_router(
    enterprise.router,
    dependencies=[Depends(require_permission(Permission.ENTERPRISE_READ))],
)
# Connectors: the tenant-independent capability catalog is authentication-only;
# tenant-scoped connector reads enforce CONNECTORS_READ per route.
router.include_router(connectors.router)
router.include_router(
    delivery_graph.router,
    dependencies=[Depends(require_permission(Permission.GRAPH_READ))],
)
router.include_router(
    predictions.router,
    dependencies=[Depends(require_permission(Permission.PREDICTIONS_READ))],
)
router.include_router(
    scenarios.router,
    dependencies=[Depends(require_permission(Permission.SCENARIOS_READ))],
)
router.include_router(
    chief_of_staff.router,
    dependencies=[Depends(require_permission(Permission.CHIEF_OF_STAFF_READ))],
)
router.include_router(security.router)
# Observability + AI quality: each route enforces its own permission
# (observability.read/manage, ai_quality.read/evaluate) via require_permission.
router.include_router(observability.router)
