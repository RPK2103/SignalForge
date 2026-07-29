"""Version 3 API router — enterprise data foundation + connectors + graph + prediction."""

from fastapi import APIRouter

from app.api.v3 import connectors, delivery_graph, enterprise, predictions

router = APIRouter()
router.include_router(enterprise.router)
router.include_router(connectors.router)
router.include_router(delivery_graph.router)
router.include_router(predictions.router)
