"""Thin orchestration layer between the v2 API and intelligence domain services."""

import hashlib
import json

from fastapi import HTTPException

from app.domain.evidence import deduplicate_team
from app.domain.models import ReadinessAssessmentRequest, TeamComposition
from app.domain.policy import DEFAULT_POLICY_VERSION, get_policy
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.api_v2 import ReadinessAssessRequest, ReadinessAssessResponse
from app.services.intelligence.readiness_assessment_service import ReadinessAssessmentService


class ReadinessOrchestrator:
    def __init__(
        self,
        catalog: CatalogRepository,
        assessment_service: ReadinessAssessmentService | None = None,
    ) -> None:
        self._catalog = catalog
        self._assessment_service = assessment_service or ReadinessAssessmentService()

    def assess(self, request: ReadinessAssessRequest) -> ReadinessAssessResponse:
        if request.policy_version is not None:
            try:
                get_policy(request.policy_version)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        project = self._catalog.get_domain_project_by_id(request.project_id)
        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project '{request.project_id}' not found",
            )

        engineers = []
        for engineer_id in request.engineer_ids:
            engineer = self._catalog.get_domain_engineer_by_id(engineer_id)
            if engineer is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Engineer '{engineer_id}' not found",
                )
            engineers.append(engineer)

        domain_request = ReadinessAssessmentRequest(
            project=project,
            team=TeamComposition(engineers=engineers),
        )
        policy_version = request.policy_version or DEFAULT_POLICY_VERSION
        assessment = self._assessment_service.assess(
            domain_request,
            policy_version=request.policy_version,
        )
        unique_team, _duplicate_ids = deduplicate_team(engineers)

        return ReadinessAssessResponse(
            assessment_id=_build_assessment_id(
                request.project_id,
                request.engineer_ids,
                policy_version,
            ),
            team=unique_team,
            **assessment.model_dump(),
        )


def _build_assessment_id(
    project_id: str,
    engineer_ids: list[str],
    policy_version: str,
) -> str:
    """Build a stable fingerprint from canonical request inputs."""
    canonical = {
        "project_id": project_id.strip().lower(),
        "engineer_ids": sorted(
            {
                engineer_id.strip().lower()
                for engineer_id in engineer_ids
                if engineer_id.strip()
            }
        ),
        "policy_version": policy_version,
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
