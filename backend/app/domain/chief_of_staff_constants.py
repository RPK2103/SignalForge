"""Chief of Staff scope policy and version constants (Phase 3 Prompt 6)."""

from __future__ import annotations

from app.domain.chief_of_staff_enums import ChiefOfStaffIntent, ChiefOfStaffSection

EVIDENCE_SCOPE_VERSION = "cos-evidence-v1"
EVIDENCE_SCHEMA_VERSION = "chief-of-staff-evidence-v1"
OUTPUT_SCHEMA_VERSION = "chief-of-staff-brief-v1"
PROMPT_VERSION = "chief-of-staff-v1"
FALLBACK_TEMPLATE_VERSION = "chief-of-staff-fallback-v1"
DECISION_OPTION_TAXONOMY_VERSION = "decision-options-v1"

SUPPORTED_HORIZONS: frozenset[int] = frozenset({30, 60, 90, 180})
DEFAULT_HORIZON_DAYS = 90

MAX_TARGETS = 1
MAX_PRIOR_BRIEFS = 1
MAX_DETERMINISTIC_RISKS = 20
MAX_GRAPH_FINDINGS = 20
MAX_EVIDENCE_SIGNALS = 40
MAX_SCENARIO_RUNS = 10
MAX_SCENARIO_IMPACTS = 100
MAX_DECISION_OPTION_CANDIDATES = 10
MAX_CLAIMS = 30
MAX_CITATIONS_PER_CLAIM = 5
MAX_REQUESTED_SECTIONS = 8
MAX_EVIDENCE_SUMMARY_CHARS = 500
MAX_CLAIM_TEXT_CHARS = 1000
MAX_PROVIDER_OUTPUT_CHARS = 50_000
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
MAX_REVIEW_NOTES_CHARS = 2000
MAX_DECISION_OPTION_RATIONALE_CHARS = 500

INTENT_REQUIRES_PRIOR_BRIEF: frozenset[ChiefOfStaffIntent] = frozenset(
    {ChiefOfStaffIntent.CHANGE_SINCE_LAST_REVIEW}
)

INTENT_ALLOWS_SCENARIO_RUNS: frozenset[ChiefOfStaffIntent] = frozenset(
    {ChiefOfStaffIntent.SCENARIO_COMPARISON_BRIEF}
)

INTENT_DEFAULT_SECTIONS: dict[ChiefOfStaffIntent, tuple[ChiefOfStaffSection, ...]] = {
    ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF: (
        ChiefOfStaffSection.EXECUTIVE_SUMMARY,
        ChiefOfStaffSection.CURRENT_POSTURE,
        ChiefOfStaffSection.TOP_DELIVERY_RISKS,
        ChiefOfStaffSection.DECISION_OPTIONS,
        ChiefOfStaffSection.EVIDENCE_GAPS,
        ChiefOfStaffSection.QUESTIONS_FOR_LEADERSHIP,
        ChiefOfStaffSection.LIMITATIONS,
        ChiefOfStaffSection.PROVIDER_PROVENANCE,
    ),
    ChiefOfStaffIntent.CHANGE_SINCE_LAST_REVIEW: (
        ChiefOfStaffSection.EXECUTIVE_SUMMARY,
        ChiefOfStaffSection.MATERIAL_CHANGES,
        ChiefOfStaffSection.CURRENT_POSTURE,
        ChiefOfStaffSection.DECISION_OPTIONS,
        ChiefOfStaffSection.QUESTIONS_FOR_LEADERSHIP,
        ChiefOfStaffSection.LIMITATIONS,
        ChiefOfStaffSection.PROVIDER_PROVENANCE,
    ),
    ChiefOfStaffIntent.SCENARIO_COMPARISON_BRIEF: (
        ChiefOfStaffSection.EXECUTIVE_SUMMARY,
        ChiefOfStaffSection.SCENARIO_IMPLICATIONS,
        ChiefOfStaffSection.ESTIMATE_INTERPRETATION,
        ChiefOfStaffSection.DECISION_OPTIONS,
        ChiefOfStaffSection.LIMITATIONS,
        ChiefOfStaffSection.PROVIDER_PROVENANCE,
    ),
    ChiefOfStaffIntent.DELIVERY_PREDICTION_BRIEF: (
        ChiefOfStaffSection.EXECUTIVE_SUMMARY,
        ChiefOfStaffSection.ESTIMATE_INTERPRETATION,
        ChiefOfStaffSection.CURRENT_POSTURE,
        ChiefOfStaffSection.TOP_DELIVERY_RISKS,
        ChiefOfStaffSection.DECISION_OPTIONS,
        ChiefOfStaffSection.LIMITATIONS,
        ChiefOfStaffSection.PROVIDER_PROVENANCE,
    ),
    ChiefOfStaffIntent.EVIDENCE_GAP_BRIEF: (
        ChiefOfStaffSection.EXECUTIVE_SUMMARY,
        ChiefOfStaffSection.EVIDENCE_GAPS,
        ChiefOfStaffSection.DECISION_OPTIONS,
        ChiefOfStaffSection.QUESTIONS_FOR_LEADERSHIP,
        ChiefOfStaffSection.LIMITATIONS,
        ChiefOfStaffSection.PROVIDER_PROVENANCE,
    ),
}

# Suspicious instruction-like phrases treated as untrusted data.
PROMPT_INJECTION_MARKERS: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore the json schema",
    "reveal system prompt",
    "expose another tenant",
    "change the readiness score",
    "activate the model",
    "probability is 95%",
    "recommend firing",
    "output credentials",
    "rank employees",
)

# Responsible-language prohibited phrase patterns (defense in depth).
PROHIBITED_LANGUAGE_MARKERS: tuple[str, ...] = (
    "guaranteed delivery",
    "guarantee delivery",
    "guarantees delivery",
    "will definitely deliver",
    "causal proof",
    "proves causation",
    "fire the engineer",
    "punish the engineer",
    "rank engineers",
    "employee ranking",
    "microsoft endorses",
    "production calibrated",
    "customer validated",
    "calibrated probability of readiness",
    "readiness probability",
    "assessment confidence probability",
    "graph confidence is model confidence",
)
