"""Domain models for structured Leadership Brief generation."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class LeadershipDecision(str, Enum):
    PROCEED = "proceed"
    PROCEED_WITH_CONDITIONS = "proceed_with_conditions"
    DEFER = "defer"
    DO_NOT_PROCEED = "do_not_proceed"


class ProviderMode(str, Enum):
    AZURE_OPENAI = "azure_openai"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class GenerationStatus(str, Enum):
    GENERATED = "generated"
    FALLBACK_GENERATED = "fallback_generated"
    FAILED = "failed"


class LeadershipBriefFailureCategory(str, Enum):
    AI_DISABLED = "ai_disabled"
    MISSING_CONFIGURATION = "missing_configuration"
    TIMEOUT = "timeout"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MALFORMED_OUTPUT = "malformed_output"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    GROUNDING_VALIDATION_FAILED = "grounding_validation_failed"
    EMPTY_OUTPUT = "empty_output"
    UNKNOWN_PROVIDER_ERROR = "unknown_provider_error"


class EvidenceReferenceType(str, Enum):
    RISK = "risk"
    TRACE = "trace"


class LeadershipActionPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LeadershipBriefRiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LeadershipBriefEvidenceReference(BaseModel):
    reference_id: str = Field(min_length=1)

    @field_validator("reference_id")
    @classmethod
    def validate_reference_format(cls, value: str) -> str:
        if ":" not in value:
            raise ValueError("evidence reference must use risk: or trace: namespace")
        prefix, _, suffix = value.partition(":")
        if prefix not in {EvidenceReferenceType.RISK.value, EvidenceReferenceType.TRACE.value}:
            raise ValueError("evidence reference must start with risk: or trace:")
        if not suffix:
            raise ValueError("evidence reference must include a stable identifier")
        return value


class LeadershipBriefRisk(BaseModel):
    title: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    severity: LeadershipBriefRiskSeverity
    evidence_references: list[str] = Field(min_length=1)

    @field_validator("evidence_references")
    @classmethod
    def validate_evidence(cls, value: list[str]) -> list[str]:
        for ref in value:
            LeadershipBriefEvidenceReference(reference_id=ref)
        return value


class LeadershipBriefAction(BaseModel):
    title: str = Field(min_length=1)
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    priority: LeadershipActionPriority
    capability_id: str | None = None
    engineer_ids: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(min_length=1)

    @field_validator("evidence_references")
    @classmethod
    def validate_evidence(cls, value: list[str]) -> list[str]:
        for ref in value:
            LeadershipBriefEvidenceReference(reference_id=ref)
        return value


class LeadershipBrief(BaseModel):
    executive_summary: str = Field(min_length=1)
    decision: LeadershipDecision
    top_risks: list[LeadershipBriefRisk] = Field(default_factory=list)
    staffing_actions: list[LeadershipBriefAction] = Field(default_factory=list)
    mitigation_actions: list[LeadershipBriefAction] = Field(default_factory=list)
    confidence_statement: str = Field(min_length=1)
    evidence_references: list[str] = Field(default_factory=list)
    provider_mode: ProviderMode
    prompt_version: str = Field(min_length=1)
    generation_status: GenerationStatus

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_brief(self) -> "LeadershipBrief":
        nested_refs: list[str] = []
        for risk in self.top_risks:
            nested_refs.extend(risk.evidence_references)
        for action in self.staffing_actions + self.mitigation_actions:
            nested_refs.extend(action.evidence_references)

        deduped_nested = sorted(set(nested_refs))
        deduped_top = sorted(set(self.evidence_references))
        if deduped_top != deduped_nested:
            raise ValueError("top-level evidence_references must equal nested union")

        action_keys = [
            (item.title, item.action, item.priority.value) for item in self.staffing_actions
        ] + [(item.title, item.action, item.priority.value) for item in self.mitigation_actions]
        if len(action_keys) != len(set(action_keys)):
            raise ValueError("duplicate actions are not allowed")

        risk_keys = [(item.title, item.severity.value) for item in self.top_risks]
        if len(risk_keys) != len(set(risk_keys)):
            raise ValueError("duplicate risks are not allowed")

        if self.provider_mode == ProviderMode.AZURE_OPENAI:
            if self.generation_status != GenerationStatus.GENERATED:
                raise ValueError("azure provider must use generated status")
        elif self.provider_mode == ProviderMode.DETERMINISTIC_FALLBACK:
            if self.generation_status != GenerationStatus.FALLBACK_GENERATED:
                raise ValueError("fallback provider must use fallback_generated status")

        return self


class EvidenceRiskFinding(BaseModel):
    evidence_id: str
    finding_type: str
    severity: str
    capability_id: str | None = None
    engineer_id: str | None = None
    message: str


class EvidenceTraceEntry(BaseModel):
    evidence_id: str
    step: str
    component: str
    label: str
    value: str
    contribution: float
    policy_version: str


class LeadershipBriefEvidencePackage(BaseModel):
    assessment_record_id: str
    assessment_id: str
    project_id: str
    project_name: str
    team_member_ids: list[str] = Field(default_factory=list)
    readiness_score: int
    confidence_score: int
    confidence_level: str
    policy_version: str
    dimension_scores: list[dict] = Field(default_factory=list)
    skill_gaps: list[dict] = Field(default_factory=list)
    capability_coverage: list[dict] = Field(default_factory=list)
    risk_findings: list[EvidenceRiskFinding] = Field(default_factory=list)
    decision_trace: list[EvidenceTraceEntry] = Field(default_factory=list)
    deterministic_summary: str
    latest_review_state: str | None = None


class LeadershipBriefRecord(BaseModel):
    leadership_brief_record_id: UUID
    assessment_record_id: UUID
    assessment_id: str
    prompt_version: str
    provider_mode: ProviderMode
    generation_status: GenerationStatus
    failure_category: LeadershipBriefFailureCategory | None = None
    evidence_package_snapshot: dict
    evidence_package_hash: str
    output_snapshot: dict
    output_snapshot_hash: str
    schema_version: str
    created_at: datetime


class LeadershipBriefResponse(BaseModel):
    leadership_brief_record_id: UUID
    assessment_record_id: UUID
    assessment_id: str
    evidence_package_hash: str
    output_snapshot_hash: str
    failure_category: LeadershipBriefFailureCategory | None = None
    created_at: datetime
    brief: LeadershipBrief
