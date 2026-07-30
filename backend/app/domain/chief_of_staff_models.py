"""Chief of Staff domain contracts (Phase 3 Prompt 6).

Strict, versioned structured contracts for request → evidence package → brief.
AI never recalculates readiness, graph findings, predictions, or scenario impacts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.chief_of_staff_constants import (
    DEFAULT_HORIZON_DAYS,
    EVIDENCE_SCHEMA_VERSION,
    EVIDENCE_SCOPE_VERSION,
    INTENT_ALLOWS_SCENARIO_RUNS,
    INTENT_DEFAULT_SECTIONS,
    INTENT_REQUIRES_PRIOR_BRIEF,
    MAX_CITATIONS_PER_CLAIM,
    MAX_CLAIM_TEXT_CHARS,
    MAX_CLAIMS,
    MAX_DECISION_OPTION_CANDIDATES,
    MAX_DECISION_OPTION_RATIONALE_CHARS,
    MAX_DETERMINISTIC_RISKS,
    MAX_EVIDENCE_SIGNALS,
    MAX_EVIDENCE_SUMMARY_CHARS,
    MAX_GRAPH_FINDINGS,
    MAX_PRIOR_BRIEFS,
    MAX_REQUESTED_SECTIONS,
    MAX_REVIEW_NOTES_CHARS,
    MAX_SCENARIO_IMPACTS,
    MAX_SCENARIO_RUNS,
    OUTPUT_SCHEMA_VERSION,
    SUPPORTED_HORIZONS,
)
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffClaimAuthorship,
    ChiefOfStaffClaimSupportStatus,
    ChiefOfStaffClaimType,
    ChiefOfStaffFailureCategory,
    ChiefOfStaffGenerationState,
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffReviewState,
    ChiefOfStaffSection,
    ChiefOfStaffTargetType,
    CitationResult,
    DecisionOptionType,
    EvidenceEntryType,
    GroundingResult,
)
from app.domain.prediction_enums import EstimateKind


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _bound_text(value: str, limit: int) -> str:
    text = (value or "").strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


class ChiefOfStaffRequest(BaseModel):
    """Trusted service/CLI request — no free-form user question."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=2, max_length=64)
    intent: ChiefOfStaffIntent
    target_type: ChiefOfStaffTargetType
    target_id: str = Field(min_length=1, max_length=64)
    as_of_at: datetime
    horizon_days: int | None = None
    scenario_run_ids: list[str] = Field(default_factory=list, max_length=MAX_SCENARIO_RUNS)
    prior_brief_id: str | None = Field(default=None, max_length=64)
    requested_sections: list[ChiefOfStaffSection] = Field(
        default_factory=list, max_length=MAX_REQUESTED_SECTIONS
    )
    requested_provider: ChiefOfStaffProviderMode = ChiefOfStaffProviderMode.AZURE_OPENAI
    evidence_scope_version: str = EVIDENCE_SCOPE_VERSION

    @field_validator("as_of_at")
    @classmethod
    def _utc_as_of(cls, value: datetime) -> datetime:
        return _ensure_utc(value)

    @field_validator("scenario_run_ids")
    @classmethod
    def _bound_scenario_ids(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_SCENARIO_RUNS:
            raise ValueError(f"scenario_run_ids exceeds maximum of {MAX_SCENARIO_RUNS}")
        cleaned = [v.strip() for v in value if v and v.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("scenario_run_ids must be unique")
        return cleaned

    @field_validator("requested_sections")
    @classmethod
    def _bound_sections(cls, value: list[ChiefOfStaffSection]) -> list[ChiefOfStaffSection]:
        if len(value) > MAX_REQUESTED_SECTIONS:
            raise ValueError(f"requested_sections exceeds maximum of {MAX_REQUESTED_SECTIONS}")
        if len(value) != len(set(value)):
            raise ValueError("requested_sections must be unique")
        return value

    @field_validator("horizon_days")
    @classmethod
    def _validate_horizon(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in SUPPORTED_HORIZONS:
            raise ValueError(
                f"Unsupported horizon_days={value}; supported={sorted(SUPPORTED_HORIZONS)}"
            )
        return value

    @model_validator(mode="after")
    def _compatibility(self) -> ChiefOfStaffRequest:
        if self.evidence_scope_version != EVIDENCE_SCOPE_VERSION:
            raise ValueError(f"Unsupported evidence_scope_version={self.evidence_scope_version}")

        requires_prior = self.intent in INTENT_REQUIRES_PRIOR_BRIEF
        if requires_prior and not self.prior_brief_id:
            raise ValueError(f"prior_brief_id is required for intent={self.intent.value}")
        if not requires_prior and self.prior_brief_id:
            raise ValueError(f"prior_brief_id is not accepted for intent={self.intent.value}")
        if self.prior_brief_id is not None:
            # Explicit max-one prior brief (scalar field already enforces).
            _ = MAX_PRIOR_BRIEFS

        allows_scenarios = self.intent in INTENT_ALLOWS_SCENARIO_RUNS
        if self.scenario_run_ids and not allows_scenarios:
            raise ValueError(f"scenario_run_ids are not accepted for intent={self.intent.value}")
        if allows_scenarios and not self.scenario_run_ids:
            raise ValueError(f"scenario_run_ids are required for intent={self.intent.value}")

        if self.intent == ChiefOfStaffIntent.DELIVERY_PREDICTION_BRIEF:
            if self.horizon_days is None:
                object.__setattr__(self, "horizon_days", DEFAULT_HORIZON_DAYS)

        if not self.requested_sections:
            object.__setattr__(
                self,
                "requested_sections",
                list(INTENT_DEFAULT_SECTIONS[self.intent]),
            )
        return self

    def resolved_sections(self) -> list[ChiefOfStaffSection]:
        return list(self.requested_sections or INTENT_DEFAULT_SECTIONS[self.intent])


class EvidenceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=128)
    evidence_type: EvidenceEntryType
    source_type: str = Field(min_length=1, max_length=64)
    source_record_id: str = Field(min_length=1, max_length=128)
    source_event_time: datetime | None = None
    observed_at: datetime | None = None
    ingested_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    summary: str = Field(min_length=1, max_length=MAX_EVIDENCE_SUMMARY_CHARS)
    semantic_classification: str = Field(min_length=1, max_length=64)
    provenance: str = Field(min_length=1, max_length=128)
    payload_hash: str = Field(min_length=8, max_length=64)
    tenant_id: str = Field(min_length=2, max_length=64)

    @field_validator("summary")
    @classmethod
    def _bound_summary(cls, value: str) -> str:
        return _bound_text(value, MAX_EVIDENCE_SUMMARY_CHARS)

    @field_validator(
        "source_event_time",
        "observed_at",
        "ingested_at",
        "valid_from",
        "valid_to",
        mode="before",
    )
    @classmethod
    def _utc_optional(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return _ensure_utc(value)
        return value


class TruncationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risks_truncated: bool = False
    risks_total: int = 0
    risks_included: int = 0
    graph_findings_truncated: bool = False
    graph_findings_total: int = 0
    graph_findings_included: int = 0
    evidence_signals_truncated: bool = False
    evidence_signals_total: int = 0
    evidence_signals_included: int = 0
    scenario_runs_truncated: bool = False
    scenario_runs_total: int = 0
    scenario_runs_included: int = 0
    scenario_impacts_truncated: bool = False
    scenario_impacts_total: int = 0
    scenario_impacts_included: int = 0

    @property
    def any_truncated(self) -> bool:
        return any(
            (
                self.risks_truncated,
                self.graph_findings_truncated,
                self.evidence_signals_truncated,
                self.scenario_runs_truncated,
                self.scenario_impacts_truncated,
            )
        )


class FreshnessSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_state: str = "unknown"
    oldest_event_time: datetime | None = None
    newest_event_time: datetime | None = None
    stale_source_count: int = 0
    aging_source_count: int = 0
    fresh_source_count: int = 0
    notes: list[str] = Field(default_factory=list, max_length=20)


class ScenarioComparability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparable: bool
    reason: str = ""
    estimate_kinds: list[str] = Field(default_factory=list)
    shared_horizon_days: int | None = None


class PredictionProvenanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_id: str | None = None
    estimate_kind: EstimateKind | None = None
    probability: float | None = None
    uncalibrated_score: float | None = None
    model_id: str | None = None
    model_state: str | None = None
    model_was_promoted: bool = False
    horizon_days: int | None = None
    as_of_at: datetime | None = None
    notes: list[str] = Field(default_factory=list, max_length=10)


class TargetLifecycleInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: ChiefOfStaffTargetType
    target_id: str
    display_name: str = Field(max_length=200)
    lifecycle_state: str = "active"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    archived_at: datetime | None = None
    criticality: str | None = None


class DeterministicChangeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str
    change_class: str  # addition | removal | material_change
    evidence_type: EvidenceEntryType
    current_evidence_id: str | None = None
    prior_evidence_id: str | None = None
    summary: str = Field(max_length=MAX_EVIDENCE_SUMMARY_CHARS)


class DecisionOptionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_type: DecisionOptionType
    eligible: bool
    rationale: str = Field(max_length=MAX_DECISION_OPTION_RATIONALE_CHARS)
    supporting_evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    advisory: bool = True


class PriorBriefReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief_id: str
    run_id: str
    as_of_at: datetime
    evidence_package_hash: str
    output_hash: str
    intent: ChiefOfStaffIntent


class ChiefOfStaffEvidencePackage(BaseModel):
    """Immutable evidence package once persisted."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = EVIDENCE_SCHEMA_VERSION
    tenant_id: str
    target_type: ChiefOfStaffTargetType
    target_id: str
    target_stable_id: str
    as_of_at: datetime
    intent: ChiefOfStaffIntent
    horizon_days: int | None = None
    target_lifecycle: TargetLifecycleInfo
    readiness_score: float | None = None
    assessment_confidence: float | None = None
    assessment_evidence_id: str | None = None
    deterministic_risks: list[EvidenceEntry] = Field(
        default_factory=list, max_length=MAX_DETERMINISTIC_RISKS
    )
    graph_findings: list[EvidenceEntry] = Field(default_factory=list, max_length=MAX_GRAPH_FINDINGS)
    prediction: PredictionProvenanceSummary | None = None
    prediction_evidence_id: str | None = None
    scenario_runs: list[EvidenceEntry] = Field(default_factory=list, max_length=MAX_SCENARIO_RUNS)
    scenario_impacts: list[EvidenceEntry] = Field(
        default_factory=list, max_length=MAX_SCENARIO_IMPACTS
    )
    scenario_comparability: ScenarioComparability | None = None
    evidence_signals: list[EvidenceEntry] = Field(
        default_factory=list, max_length=MAX_EVIDENCE_SIGNALS
    )
    freshness_summary: FreshnessSummary = Field(default_factory=FreshnessSummary)
    missing_data_warnings: list[str] = Field(default_factory=list, max_length=20)
    contradiction_warnings: list[str] = Field(default_factory=list, max_length=20)
    prior_brief: PriorBriefReference | None = None
    deterministic_changes: list[DeterministicChangeRecord] = Field(
        default_factory=list, max_length=50
    )
    decision_option_candidates: list[DecisionOptionCandidate] = Field(
        default_factory=list, max_length=MAX_DECISION_OPTION_CANDIDATES
    )
    truncation: TruncationMetadata = Field(default_factory=TruncationMetadata)
    evidence_entries: list[EvidenceEntry] = Field(default_factory=list, max_length=250)
    package_hash: str = ""

    @field_validator("as_of_at")
    @classmethod
    def _utc_as_of(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class ChiefOfStaffClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=64)
    claim_type: ChiefOfStaffClaimType
    text: str = Field(min_length=1, max_length=MAX_CLAIM_TEXT_CHARS)
    support_status: ChiefOfStaffClaimSupportStatus
    authorship: ChiefOfStaffClaimAuthorship
    temporal_cutoff: datetime
    evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_CITATIONS_PER_CLAIM)
    semantic_metadata: dict[str, Any] = Field(default_factory=dict)
    ordering_index: int = Field(ge=0, lt=MAX_CLAIMS)

    @field_validator("text")
    @classmethod
    def _bound_claim_text(cls, value: str) -> str:
        return _bound_text(value, MAX_CLAIM_TEXT_CHARS)


class ChiefOfStaffCitation(BaseModel):
    """Semantic citation. ``package_id`` is the content-canonical evidence package hash.

    Persistence stores the evidence-snapshot FK separately; it must not appear in
    semantic structured output or ``output_hash``.
    """

    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(min_length=1, max_length=64)
    claim_id: str = Field(min_length=1, max_length=64)
    evidence_id: str = Field(min_length=1, max_length=128)
    evidence_type: EvidenceEntryType
    package_id: str = Field(
        min_length=1,
        max_length=64,
        description="Content-canonical evidence_package_hash (not a DB snapshot PK)",
    )
    ordering_index: int = Field(ge=0, lt=MAX_CITATIONS_PER_CLAIM)


class ChiefOfStaffBriefSectionContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: ChiefOfStaffSection
    text: str = Field(max_length=4000)
    claim_ids: list[str] = Field(default_factory=list, max_length=MAX_CLAIMS)


class ChiefOfStaffBrief(BaseModel):
    """Strict versioned structured brief output."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = OUTPUT_SCHEMA_VERSION
    intent: ChiefOfStaffIntent
    target_type: ChiefOfStaffTargetType
    target_id: str
    as_of_at: datetime
    horizon_days: int | None = None
    sections: list[ChiefOfStaffBriefSectionContent] = Field(default_factory=list, max_length=20)
    claims: list[ChiefOfStaffClaim] = Field(default_factory=list, max_length=MAX_CLAIMS)
    citations: list[ChiefOfStaffCitation] = Field(default_factory=list, max_length=150)
    decision_option_types: list[DecisionOptionType] = Field(
        default_factory=list, max_length=MAX_DECISION_OPTION_CANDIDATES
    )
    estimate_kind: EstimateKind | None = None
    probability: float | None = None
    uncalibrated_score: float | None = None
    provider_mode: ChiefOfStaffProviderMode
    generation_state: ChiefOfStaffGenerationState
    fallback_visible: bool = False
    limitations: list[str] = Field(default_factory=list, max_length=20)
    synthetic_demo_scope: bool = False

    @model_validator(mode="after")
    def _estimate_semantics(self) -> ChiefOfStaffBrief:
        if self.estimate_kind == EstimateKind.UNCALIBRATED_SCORE and self.probability is not None:
            raise ValueError("probability must be null for uncalibrated_score")
        if self.estimate_kind == EstimateKind.CALIBRATED_PROBABILITY and self.probability is None:
            raise ValueError("probability required for calibrated_probability")
        if len(self.claims) != len({c.claim_id for c in self.claims}):
            raise ValueError("duplicate claim_id")
        if len(self.citations) != len({c.citation_id for c in self.citations}):
            raise ValueError("duplicate citation_id")
        return self


class ChiefOfStaffReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str
    tenant_id: str
    brief_id: str
    review_state: ChiefOfStaffReviewState
    reviewer_context: str = Field(max_length=64)
    notes: str = Field(default="", max_length=MAX_REVIEW_NOTES_CHARS)
    created_at: datetime


class ChiefOfStaffRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    run_id: str
    tenant_id: str
    target_type: ChiefOfStaffTargetType
    target_id: str
    intent: ChiefOfStaffIntent
    as_of_at: datetime
    horizon_days: int | None = None
    evidence_snapshot_id: str
    prior_brief_id: str | None = None
    requested_provider: ChiefOfStaffProviderMode
    final_provider: ChiefOfStaffProviderMode
    model_deployment_id: str | None = None
    prompt_version: str
    evidence_schema_version: str
    output_schema_version: str
    fallback_template_version: str
    evidence_package_hash: str
    output_hash: str | None = None
    generation_state: ChiefOfStaffGenerationState
    failure_category: ChiefOfStaffFailureCategory | None = None
    grounding_result: GroundingResult | None = None
    citation_result: CitationResult | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    provider_latency_ms: int | None = None
    duration_ms: int | None = None
    correlation_id: str
    created_at: datetime


class ChiefOfStaffBriefRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    brief_id: str
    tenant_id: str
    run_id: str
    evidence_snapshot_id: str
    target_type: ChiefOfStaffTargetType
    target_id: str
    intent: ChiefOfStaffIntent
    as_of_at: datetime
    horizon_days: int | None = None
    brief_json: dict[str, Any]
    output_hash: str
    output_schema_version: str
    generation_state: ChiefOfStaffGenerationState
    final_provider: ChiefOfStaffProviderMode
    estimate_kind: EstimateKind | None = None
    probability: float | None = None
    created_at: datetime


class ChiefOfStaffEvidenceSnapshotRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    snapshot_id: str
    tenant_id: str
    target_type: ChiefOfStaffTargetType
    target_id: str
    intent: ChiefOfStaffIntent
    as_of_at: datetime
    horizon_days: int | None = None
    evidence_schema_version: str
    package_hash: str
    package_json: dict[str, Any]
    truncation_flags: dict[str, Any]
    created_at: datetime


class QualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    total_runs: int = 0
    generated_count: int = 0
    fallback_count: int = 0
    fallback_rate: float = 0.0
    failed_count: int = 0
    rejected_count: int = 0
    failure_categories: dict[str, int] = Field(default_factory=dict)
    grounding_failures: int = 0
    citation_failures: int = 0
    unsupported_claim_detections: int = 0
    prompt_injection_detections: int = 0
    provider_latency_ms_avg: float | None = None
    provider_latency_ms_max: int | None = None
    total_tokens_sum: int | None = None


class GenerationOutcome(BaseModel):
    """Service-layer generation result (not persisted as-is)."""

    model_config = ConfigDict(extra="forbid")

    run: ChiefOfStaffRunRecord
    brief: ChiefOfStaffBriefRecord | None = None
    evidence_snapshot: ChiefOfStaffEvidenceSnapshotRecord
    package: ChiefOfStaffEvidencePackage
    structured_brief: ChiefOfStaffBrief | None = None
