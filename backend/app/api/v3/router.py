"""Version 3 API router — enterprise + connectors + graph + prediction + scenarios + CoS."""

from fastapi import APIRouter

from app.api.v3 import (
    chief_of_staff,
    connectors,
    delivery_graph,
    enterprise,
    predictions,
    scenarios,
)

router = APIRouter()
router.include_router(enterprise.router)
router.include_router(connectors.router)
router.include_router(delivery_graph.router)
router.include_router(predictions.router)
router.include_router(scenarios.router)
router.include_router(chief_of_staff.router)
