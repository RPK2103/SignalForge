"""Domain models for deterministic team simulation."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.domain.enums import (
    CoverageLevel,
    MitigationPriority,
    MitigationType,
    RiskFindingType,
    RiskSeverity,
    SimulationChangeType,
    SimulationOperationType,
)
from app.domain.models import (
    DecisionTraceEntry,
    EngineerProfile,
    ReadinessAssessmentResponse,
    RiskFinding,
    SkillGap,
)


class AddSimulationOperation(BaseModel):
    type: Literal[SimulationOperationType.ADD] = SimulationOperationType.ADD
    engineer_id: str = Field(min_length=1)


class RemoveSimulationOperation(BaseModel):
    type: Literal[SimulationOperationType.REMOVE] = SimulationOperationType.REMOVE
    engineer_id: str = Field(min_length=1)


class ReplaceSimulationOperation(BaseModel):
    type: Literal[SimulationOperationType.REPLACE] = SimulationOperationType.REPLACE
    remove_engineer_id: str = Field(min_length=1)
    add_engineer_id: str = Field(min_length=1)


class CompareSimulationOperation(BaseModel):
    type: Literal[SimulationOperationType.COMPARE] = SimulationOperationType.COMPARE
    proposed_engineer_ids: list[str] = Field(default_factory=list)


SimulationOperation = Annotated[
    Union[
        AddSimulationOperation,
        RemoveSimulationOperation,
        ReplaceSimulationOperation,
        CompareSimulationOperation,
    ],
    Field(discriminator="type"),
]


class SimulationTeamSnapshot(BaseModel):
    engineer_ids: list[str] = Field(default_factory=list)
    engineers: list[EngineerProfile] = Field(default_factory=list)


class RiskFindingChange(BaseModel):
    change_type: SimulationChangeType
    finding_type: RiskFindingType
    severity: RiskSeverity
    baseline_severity: RiskSeverity | None = None
    proposed_severity: RiskSeverity | None = None
    capability_id: str | None = None
    engineer_id: str | None = None
    message: str


class CapabilityCoverageChange(BaseModel):
    change_type: SimulationChangeType
    capability_id: str
    capability_name: str
    baseline_level: CoverageLevel
    proposed_level: CoverageLevel
    baseline_effective_score: int = Field(ge=0, le=100)
    proposed_effective_score: int = Field(ge=0, le=100)
    score_delta: int
    affected_engineer_ids: list[str] = Field(default_factory=list)
    is_critical: bool = False


class KeyPersonDependencyChange(BaseModel):
    change_type: SimulationChangeType
    capability_id: str
    capability_name: str
    baseline_covering_engineer_ids: list[str] = Field(default_factory=list)
    proposed_covering_engineer_ids: list[str] = Field(default_factory=list)
    baseline_is_dependency: bool = False
    proposed_is_dependency: bool = False
    is_critical: bool = False


class DecisionTraceDelta(BaseModel):
    trace_key: str
    step: str
    component: str
    label: str
    baseline_contribution: float
    proposed_contribution: float
    contribution_delta: float
    baseline_value: str
    proposed_value: str


class DeterministicMitigation(BaseModel):
    mitigation_id: str
    mitigation_type: MitigationType
    priority: MitigationPriority
    title: str
    action: str
    rationale: str
    capability_id: str | None = None
    affected_engineer_ids: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    policy_version: str


class SimulationResult(BaseModel):
    project_id: str
    operation: SimulationOperation
    baseline_team: SimulationTeamSnapshot
    proposed_team: SimulationTeamSnapshot
    baseline_assessment: ReadinessAssessmentResponse
    proposed_assessment: ReadinessAssessmentResponse
    readiness_score_delta: int
    confidence_delta: int
    risk_level_changes: list[RiskFindingChange] = Field(default_factory=list)
    capability_coverage_changes: list[CapabilityCoverageChange] = Field(
        default_factory=list
    )
    newly_introduced_gaps: list[SkillGap] = Field(default_factory=list)
    resolved_gaps: list[SkillGap] = Field(default_factory=list)
    key_person_dependency_changes: list[KeyPersonDependencyChange] = Field(
        default_factory=list
    )
    decision_trace_delta: list[DecisionTraceDelta] = Field(default_factory=list)
    recommended_mitigations: list[DeterministicMitigation] = Field(
        default_factory=list
    )
    policy_version: str


def risk_finding_key(finding: RiskFinding) -> tuple[str, str, str]:
    return (
        finding.finding_type.value,
        finding.capability_id or "",
        finding.engineer_id or "",
    )


def skill_gap_key(gap: SkillGap) -> tuple[str, str]:
    return (gap.capability_id, gap.level.value)


def trace_entry_key(entry: DecisionTraceEntry) -> tuple[str, str, str]:
    return (entry.step, entry.component, entry.label)
