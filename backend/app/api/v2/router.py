"""Version 2 API router — production readiness intelligence surface."""

from fastapi import APIRouter

from app.api.v2 import (
    assessments,
    capabilities,
    catalog,
    readiness,
    simulation_records,
    simulations,
)

router = APIRouter(prefix="/api/v2")
router.include_router(readiness.router)
router.include_router(simulations.router)
router.include_router(assessments.router)
router.include_router(simulation_records.router)
router.include_router(capabilities.router)
router.include_router(catalog.router)
