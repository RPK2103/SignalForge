"""Version 3 API router — enterprise data foundation."""

from fastapi import APIRouter

from app.api.v3 import enterprise

router = APIRouter()
router.include_router(enterprise.router)
