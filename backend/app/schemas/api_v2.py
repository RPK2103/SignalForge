"""Request and response schemas for the versioned readiness API."""

from pydantic import BaseModel, Field

from app.domain.models import (
    CapabilityDefinition,
    EngineerProfile,
    ProjectProfile,
    ReadinessAssessmentResponse,
    SkillGap,
)
from app.domain.simulation_models import (
    CapabilityCoverageChange,
    DecisionTraceDelta,
    DeterministicMitigation,
    KeyPersonDependencyChange,
    RiskFindingChange,
    SimulationOperation,
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


class SimulationRequest(BaseModel):
    project_id: str = Field(min_length=1)
    baseline_engineer_ids: list[str] = Field(default_factory=list)
    operation: SimulationOperation
    policy_version: str | None = None


class SimulationResponse(BaseModel):
    simulation_id: str
    project_id: str
    operation: SimulationOperation
    baseline_team: list[EngineerProfile] = Field(default_factory=list)
    proposed_team: list[EngineerProfile] = Field(default_factory=list)
    baseline_assessment: ReadinessAssessResponse
    proposed_assessment: ReadinessAssessResponse
    readiness_score_delta: int
    confidence_delta: int
    risk_level_changes: list[RiskFindingChange] = Field(default_factory=list)
    capability_coverage_changes: list[CapabilityCoverageChange] = Field(default_factory=list)
    newly_introduced_gaps: list[SkillGap] = Field(default_factory=list)
    resolved_gaps: list[SkillGap] = Field(default_factory=list)
    key_person_dependency_changes: list[KeyPersonDependencyChange] = Field(default_factory=list)
    decision_trace_delta: list[DecisionTraceDelta] = Field(default_factory=list)
    recommended_mitigations: list[DeterministicMitigation] = Field(default_factory=list)
    policy_version: str
