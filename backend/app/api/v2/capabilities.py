"""Capability catalog routes for the v2 API."""

from fastapi import APIRouter

from app.domain.capability_registry import all_capabilities
from app.schemas.api_v2 import CapabilityListResponse

router = APIRouter(prefix="/capabilities", tags=["Capability Catalog"])


@router.get("", response_model=CapabilityListResponse)
def list_capabilities() -> CapabilityListResponse:
    return CapabilityListResponse(capabilities=all_capabilities())
