"""Version 3 API router — enterprise data foundation + connector observation."""

from fastapi import APIRouter

from app.api.v3 import connectors, enterprise

router = APIRouter()
router.include_router(enterprise.router)
router.include_router(connectors.router)
