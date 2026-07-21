from pydantic import BaseModel, Field

from app.domain.enums import (
    CapabilityCategory,
    ConfidenceLevel,
    CoverageLevel,
    EvidenceSource,
    ReadinessDimension,
    RiskFindingType,
    RiskSeverity,
)


class CapabilityDefinition(BaseModel):
    id: str
    name: str
    category: CapabilityCategory
    keywords: list[str] = Field(default_factory=list)


class EngineerCapability(BaseModel):
    capability_id: str
    proficiency: int = Field(ge=0, le=100)
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)


class EngineerProfile(BaseModel):
    id: str
    name: str
    experience_years: float = Field(ge=0)
    capabilities: list[EngineerCapability] = Field(default_factory=list)
    has_certifications: bool = True
    has_project_history: bool = True


class ProjectRequirement(BaseModel):
    capability_id: str
    weight: float = Field(default=1.0, gt=0)
    critical: bool = False


class ProjectProfile(BaseModel):
    id: str
    name: str
    requirements: list[ProjectRequirement] = Field(default_factory=list)


class TeamComposition(BaseModel):
    engineers: list[EngineerProfile] = Field(default_factory=list)


class CoverageResult(BaseModel):
    capability_id: str
    capability_name: str
    category: CapabilityCategory
    level: CoverageLevel
    team_proficiency: int = Field(ge=0, le=100)
    covering_engineer_ids: list[str] = Field(default_factory=list)
    is_critical: bool = False
    weight: float = 1.0


class SkillGap(BaseModel):
    capability_id: str
    capability_name: str
    category: CapabilityCategory
    level: CoverageLevel
    is_critical: bool = False
    weight: float = 1.0
    covering_engineer_count: int = 0


class RiskFinding(BaseModel):
    finding_type: RiskFindingType
    severity: RiskSeverity
    capability_id: str | None = None
    engineer_id: str | None = None
    message: str


class ReadinessDimensionScore(BaseModel):
    dimension: ReadinessDimension
    score: int = Field(ge=0, le=100)
    weight: float = Field(gt=0)


class DecisionTraceEntry(BaseModel):
    step: str
    component: str
    label: str
    value: str
    contribution: float
    policy_version: str


class ReadinessAssessmentRequest(BaseModel):
    project: ProjectProfile
    team: TeamComposition


class ReadinessAssessmentResponse(BaseModel):
    project_id: str
    project_name: str
    readiness_score: int = Field(ge=0, le=100)
    confidence_score: int = Field(ge=0, le=100)
    confidence_level: ConfidenceLevel
    coverage_results: list[CoverageResult] = Field(default_factory=list)
    skill_gaps: list[SkillGap] = Field(default_factory=list)
    risk_findings: list[RiskFinding] = Field(default_factory=list)
    dimension_scores: list[ReadinessDimensionScore] = Field(default_factory=list)
    decision_trace: list[DecisionTraceEntry] = Field(default_factory=list)
    policy_version: str
    summary: str
