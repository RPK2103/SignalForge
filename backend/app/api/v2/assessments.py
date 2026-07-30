"""Persisted assessment history API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import require_json_content_type
from app.api.persistence_dependencies import (
    get_assessment_persistence_service,
    get_leadership_brief_persistence_service,
    get_review_persistence_service,
)
from app.api.v3.dependencies import require_permission
from app.domain.enums import HumanReviewState
from app.domain.leadership_brief_models import LeadershipBriefResponse
from app.domain.persistence_models import AssessmentRecordResponse, PaginatedAssessmentList
from app.schemas.api_v2 import ReadinessAssessRequest
from app.security.context import SecurityContext
from app.security.enums import Permission
from app.services.persistence.assessment_persistence_service import AssessmentPersistenceService
from app.services.persistence.exceptions import PersistenceError
from app.services.persistence.leadership_brief_persistence_service import (
    LeadershipBriefPersistenceService,
)
from app.services.persistence.review_persistence_service import (
    HumanReviewPersistenceService,
    HumanReviewRequest,
)

router = APIRouter(prefix="/assessments", tags=["Assessment History"])


@router.post(
    "",
    response_model=AssessmentRecordResponse,
    dependencies=[Depends(require_json_content_type)],
)
def create_assessment(
    request: ReadinessAssessRequest,
    context: SecurityContext = Depends(require_permission(Permission.ENTERPRISE_MANAGE)),
    service: AssessmentPersistenceService = Depends(get_assessment_persistence_service),
) -> AssessmentRecordResponse:
    try:
        return service.create_assessment(context, request)
    except PersistenceError:
        raise


@router.get(
    "",
    response_model=PaginatedAssessmentList,
    dependencies=[Depends(require_permission(Permission.ENTERPRISE_READ))],
)
def list_assessments(
    project_id: str | None = Query(default=None),
    assessment_id: str | None = Query(default=None),
    review_state: HumanReviewState | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: AssessmentPersistenceService = Depends(get_assessment_persistence_service),
) -> PaginatedAssessmentList:
    try:
        return service.list_assessments(
            project_id=project_id,
            assessment_id=assessment_id,
            review_state=review_state,
            limit=limit,
            offset=offset,
        )
    except PersistenceError:
        raise


@router.get(
    "/{assessment_record_id}",
    response_model=AssessmentRecordResponse,
    dependencies=[Depends(require_permission(Permission.ENTERPRISE_READ))],
)
def get_assessment(
    assessment_record_id: UUID,
    service: AssessmentPersistenceService = Depends(get_assessment_persistence_service),
) -> AssessmentRecordResponse:
    try:
        return service.get_assessment(assessment_record_id)
    except PersistenceError:
        raise


@router.post(
    "/{assessment_record_id}/leadership-brief",
    response_model=LeadershipBriefResponse,
    operation_id="generateLeadershipBriefV2",
)
def generate_leadership_brief(
    assessment_record_id: UUID,
    context: SecurityContext = Depends(require_permission(Permission.CHIEF_OF_STAFF_GENERATE)),
    service: LeadershipBriefPersistenceService = Depends(get_leadership_brief_persistence_service),
) -> LeadershipBriefResponse:
    try:
        return service.generate_leadership_brief(context, assessment_record_id)
    except PersistenceError:
        raise


@router.get(
    "/{assessment_record_id}/leadership-briefs",
    response_model=list[LeadershipBriefResponse],
    operation_id="listLeadershipBriefsV2",
    dependencies=[Depends(require_permission(Permission.CHIEF_OF_STAFF_READ))],
)
def list_leadership_briefs(
    assessment_record_id: UUID,
    service: LeadershipBriefPersistenceService = Depends(get_leadership_brief_persistence_service),
) -> list[LeadershipBriefResponse]:
    try:
        return service.list_leadership_briefs(assessment_record_id)
    except PersistenceError:
        raise


@router.post(
    "/{assessment_record_id}/reviews",
    response_model=AssessmentRecordResponse,
    dependencies=[Depends(require_json_content_type)],
)
def create_review(
    assessment_record_id: UUID,
    request: HumanReviewRequest,
    context: SecurityContext = Depends(require_permission(Permission.CHIEF_OF_STAFF_REVIEW)),
    service: HumanReviewPersistenceService = Depends(get_review_persistence_service),
) -> AssessmentRecordResponse:
    try:
        return service.add_review(context, assessment_record_id, request)
    except PersistenceError:
        raise
