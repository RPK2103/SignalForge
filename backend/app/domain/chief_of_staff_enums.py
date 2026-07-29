"""Chief of Staff enums (Phase 3 Prompt 6).

Bounded, auditable executive-briefing domain. Not an autonomous agent.
"""

from __future__ import annotations

from enum import Enum


class ChiefOfStaffIntent(str, Enum):
    DELIVERY_STATUS_BRIEF = "delivery_status_brief"
    CHANGE_SINCE_LAST_REVIEW = "change_since_last_review"
    SCENARIO_COMPARISON_BRIEF = "scenario_comparison_brief"
    DELIVERY_PREDICTION_BRIEF = "delivery_prediction_brief"
    EVIDENCE_GAP_BRIEF = "evidence_gap_brief"


class ChiefOfStaffTargetType(str, Enum):
    PROJECT = "project"
    INITIATIVE = "initiative"


class ChiefOfStaffProviderMode(str, Enum):
    AZURE_OPENAI = "azure_openai"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class ChiefOfStaffGenerationState(str, Enum):
    GENERATED = "generated"
    FALLBACK_GENERATED = "fallback_generated"
    REJECTED = "rejected"
    FAILED = "failed"


class ChiefOfStaffFailureCategory(str, Enum):
    AI_DISABLED = "ai_disabled"
    MISSING_CONFIGURATION = "missing_configuration"
    TIMEOUT = "timeout"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MALFORMED_OUTPUT = "malformed_output"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    GROUNDING_VALIDATION_FAILED = "grounding_validation_failed"
    CITATION_VALIDATION_FAILED = "citation_validation_failed"
    UNSUPPORTED_CLAIM_DETECTED = "unsupported_claim_detected"
    PROMPT_INJECTION_DETECTED = "prompt_injection_detected"
    EMPTY_OUTPUT = "empty_output"
    OVERSIZED_OUTPUT = "oversized_output"
    UNKNOWN_PROVIDER_ERROR = "unknown_provider_error"


class ChiefOfStaffSection(str, Enum):
    EXECUTIVE_SUMMARY = "executive_summary"
    CURRENT_POSTURE = "current_posture"
    MATERIAL_CHANGES = "material_changes"
    TOP_DELIVERY_RISKS = "top_delivery_risks"
    SCENARIO_IMPLICATIONS = "scenario_implications"
    ESTIMATE_INTERPRETATION = "estimate_interpretation"
    DECISION_OPTIONS = "decision_options"
    EVIDENCE_GAPS = "evidence_gaps"
    QUESTIONS_FOR_LEADERSHIP = "questions_for_leadership"
    LIMITATIONS = "limitations"
    PROVIDER_PROVENANCE = "provider_provenance"
    FALLBACK_VISIBILITY = "fallback_visibility"
    CLAIMS = "claims"
    CITATIONS = "citations"


class ChiefOfStaffClaimType(str, Enum):
    SOURCE_FACT = "source_fact"
    DETERMINISTIC_FINDING = "deterministic_finding"
    DETERMINISTIC_CHANGE = "deterministic_change"
    PREDICTION_ESTIMATE = "prediction_estimate"
    SCENARIO_IMPLICATION = "scenario_implication"
    EVIDENCE_GAP = "evidence_gap"
    LIMITATION = "limitation"
    ADVISORY_OPTION = "advisory_option"


class ChiefOfStaffClaimSupportStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"


class ChiefOfStaffClaimAuthorship(str, Enum):
    DETERMINISTIC = "deterministic"
    AI_AUTHORED = "ai_authored"


class ChiefOfStaffReviewState(str, Enum):
    ACCEPTED = "accepted"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class DecisionOptionType(str, Enum):
    REQUEST_ADDITIONAL_EVIDENCE = "request_additional_evidence"
    VALIDATE_DEPENDENCY_OWNER = "validate_dependency_owner"
    REVIEW_CROSS_TEAM_DEPENDENCY = "review_cross_team_dependency"
    REVIEW_CAPACITY_PLAN = "review_capacity_plan"
    REVIEW_DELIVERY_HORIZON = "review_delivery_horizon"
    COMPARE_MITIGATION_SCENARIO = "compare_mitigation_scenario"
    REVIEW_INCIDENT_BURDEN = "review_incident_burden"
    DEFER_DECISION_PENDING_EVIDENCE = "defer_decision_pending_evidence"
    SCHEDULE_HUMAN_RISK_REVIEW = "schedule_human_risk_review"
    CONTINUE_MONITORING = "continue_monitoring"


class EvidenceEntryType(str, Enum):
    TARGET_METADATA = "target_metadata"
    READINESS_ASSESSMENT = "readiness_assessment"
    ASSESSMENT_RISK = "assessment_risk"
    GRAPH_FINDING = "graph_finding"
    DELIVERY_PREDICTION = "delivery_prediction"
    SCENARIO_RUN = "scenario_run"
    SCENARIO_RESULT = "scenario_result"
    SCENARIO_IMPACT = "scenario_impact"
    EVIDENCE_SIGNAL = "evidence_signal"
    FRESHNESS_SUMMARY = "freshness_summary"
    MISSING_DATA_WARNING = "missing_data_warning"
    CONTRADICTION_WARNING = "contradiction_warning"
    PRIOR_BRIEF_REFERENCE = "prior_brief_reference"
    DETERMINISTIC_CHANGE = "deterministic_change"
    DECISION_OPTION_CANDIDATE = "decision_option_candidate"
    PACKAGE_METADATA = "package_metadata"
    TRUNCATION_METADATA = "truncation_metadata"


class GroundingResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class CitationResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
