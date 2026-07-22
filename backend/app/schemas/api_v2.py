"""Request and response schemas for the versioned readiness API."""

from pydantic import BaseModel, Field

from app.domain.models import (
    CapabilityDefinition,
    EngineerProfile,
    ProjectProfile,
    ReadinessAssessmentResponse,
)


class ReadinessAssessRequest(BaseModel):
    project_id: str = Field(min_length=1)
    engineer_ids: list[str] = Field(default_factory=list)
    policy_version: str | None = None


class ReadinessAssessResponse(ReadinessAssessmentResponse):
    """API envelope extending the domain assessment with request metadata."""

    assessment_id: str
    team: list[EngineerProfile] = Field(default_factory=list)


class CapabilityListResponse(BaseModel):
    capabilities: list[CapabilityDefinition]


class EngineerListResponse(BaseModel):
    engineers: list[EngineerProfile]


class ProjectListResponse(BaseModel):
    projects: list[ProjectProfile]


class ReadinessPolicyMetadata(BaseModel):
    version: str
    description: str
    dimension_weights: dict[str, float]
    confidence_level_thresholds: dict[str, int]


class ReadinessPolicyListResponse(BaseModel):
    policies: list[ReadinessPolicyMetadata]
    default_version: str
