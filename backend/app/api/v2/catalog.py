"""Catalog and policy metadata routes for the v2 API."""

from fastapi import APIRouter, Depends

from app.domain.policy import DEFAULT_POLICY_VERSION
from app.domain.policy import v1 as policy_v1
from app.repositories import get_catalog_repository
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.api_v2 import (
    EngineerListResponse,
    ProjectListResponse,
    ReadinessPolicyListResponse,
    ReadinessPolicyMetadata,
)

router = APIRouter(tags=["Intelligence Catalog"])


@router.get("/engineers", response_model=EngineerListResponse)
def list_engineers(
    catalog: CatalogRepository = Depends(get_catalog_repository),
) -> EngineerListResponse:
    return EngineerListResponse(engineers=catalog.get_domain_engineers())


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(
    catalog: CatalogRepository = Depends(get_catalog_repository),
) -> ProjectListResponse:
    return ProjectListResponse(projects=catalog.list_domain_projects())


@router.get("/policies/readiness", response_model=ReadinessPolicyListResponse)
def list_readiness_policies() -> ReadinessPolicyListResponse:
    return ReadinessPolicyListResponse(
        default_version=DEFAULT_POLICY_VERSION,
        policies=[
            ReadinessPolicyMetadata(
                version=policy_v1.POLICY_VERSION,
                description="Deterministic readiness and confidence scoring for engineering teams.",
                dimension_weights=dict(policy_v1.DIMENSION_WEIGHTS),
                confidence_level_thresholds={
                    "high_min": policy_v1.CONFIDENCE_LEVEL_HIGH_MIN,
                    "medium_min": policy_v1.CONFIDENCE_LEVEL_MEDIUM_MIN,
                },
            )
        ],
    )
