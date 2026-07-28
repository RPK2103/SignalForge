"""Version 3 API router — enterprise data foundation + connector observation + delivery graph."""

from fastapi import APIRouter

from app.api.v3 import connectors, delivery_graph, enterprise

router = APIRouter()
router.include_router(enterprise.router)
router.include_router(connectors.router)
router.include_router(delivery_graph.router)
