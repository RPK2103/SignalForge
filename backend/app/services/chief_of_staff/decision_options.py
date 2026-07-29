"""Deterministic decision-option eligibility from evidence packages."""

from __future__ import annotations

from app.domain.chief_of_staff_constants import (
    DECISION_OPTION_TAXONOMY_VERSION,
    MAX_DECISION_OPTION_CANDIDATES,
)
from app.domain.chief_of_staff_enums import DecisionOptionType, EvidenceEntryType
from app.domain.chief_of_staff_models import (
    ChiefOfStaffEvidencePackage,
    DecisionOptionCandidate,
)


def compute_decision_options(package: ChiefOfStaffEvidencePackage) -> list[DecisionOptionCandidate]:
    """Eligibility is deterministic; provider may only phrase eligible options."""
    candidates: list[DecisionOptionCandidate] = []
    evidence_ids = {e.evidence_id for e in package.evidence_entries}

    def add(
        option: DecisionOptionType,
        eligible: bool,
        rationale: str,
        supporting: list[str],
    ) -> None:
        if len(candidates) >= MAX_DECISION_OPTION_CANDIDATES:
            return
        safe_support = [eid for eid in supporting if eid in evidence_ids][:10]
        candidates.append(
            DecisionOptionCandidate(
                option_type=option,
                eligible=eligible,
                rationale=rationale[:500],
                supporting_evidence_ids=safe_support,
                advisory=True,
            )
        )

    missing = list(package.missing_data_warnings)
    stale = package.freshness_summary.stale_source_count > 0
    risks = package.deterministic_risks
    findings = package.graph_findings
    scenarios = package.scenario_runs
    prediction = package.prediction

    gap_ids = [
        e.evidence_id
        for e in package.evidence_entries
        if e.evidence_type
        in {
            EvidenceEntryType.MISSING_DATA_WARNING,
            EvidenceEntryType.FRESHNESS_SUMMARY,
            EvidenceEntryType.TRUNCATION_METADATA,
        }
    ]
    risk_ids = [e.evidence_id for e in risks]
    finding_ids = [e.evidence_id for e in findings]
    scenario_ids = [e.evidence_id for e in scenarios]
    pred_ids = [package.prediction_evidence_id] if package.prediction_evidence_id else []

    add(
        DecisionOptionType.REQUEST_ADDITIONAL_EVIDENCE,
        bool(missing) or stale or package.truncation.any_truncated,
        "Evidence is incomplete, stale, or truncated; request additional sources.",
        gap_ids,
    )
    add(
        DecisionOptionType.VALIDATE_DEPENDENCY_OWNER,
        any("dependency" in (e.semantic_classification or "") for e in findings)
        or any("owner" in (e.summary or "").lower() for e in findings),
        "Graph findings suggest ownership or dependency validation is needed.",
        finding_ids,
    )
    add(
        DecisionOptionType.REVIEW_CROSS_TEAM_DEPENDENCY,
        any(
            "cross" in (e.semantic_classification or "")
            or "dependency" in (e.summary or "").lower()
            for e in findings + risks
        ),
        "Cross-team dependency risk is present in deterministic findings.",
        finding_ids + risk_ids,
    )
    add(
        DecisionOptionType.REVIEW_CAPACITY_PLAN,
        any("capacity" in (e.summary or "").lower() for e in risks + findings),
        "Capacity-related risk language appears in deterministic evidence.",
        risk_ids + finding_ids,
    )
    add(
        DecisionOptionType.REVIEW_DELIVERY_HORIZON,
        prediction is not None or package.horizon_days is not None,
        "Delivery horizon estimate is in scope for this brief.",
        pred_ids,
    )
    add(
        DecisionOptionType.COMPARE_MITIGATION_SCENARIO,
        bool(scenarios),
        "Scenario runs are available for advisory comparison.",
        scenario_ids,
    )
    add(
        DecisionOptionType.REVIEW_INCIDENT_BURDEN,
        any("incident" in (e.summary or "").lower() for e in package.evidence_signals + risks),
        "Incident-related evidence is present.",
        [e.evidence_id for e in package.evidence_signals][:5] + risk_ids[:3],
    )
    add(
        DecisionOptionType.DEFER_DECISION_PENDING_EVIDENCE,
        bool(missing) or stale,
        "Defer advisory decisions until missing or stale evidence is resolved.",
        gap_ids,
    )
    add(
        DecisionOptionType.SCHEDULE_HUMAN_RISK_REVIEW,
        len(risks) > 0 or len(findings) > 0,
        "Deterministic risks or graph findings warrant human risk review.",
        risk_ids[:5] + finding_ids[:5],
    )
    add(
        DecisionOptionType.CONTINUE_MONITORING,
        True,
        "Continue monitoring delivery posture; no autonomous action is authorized.",
        [
            e.evidence_id
            for e in package.evidence_entries
            if e.evidence_type == EvidenceEntryType.PACKAGE_METADATA
        ][:1]
        or gap_ids[:1]
        or risk_ids[:1],
    )

    # Stable order by option_type value then eligibility desc.
    candidates.sort(key=lambda c: (c.option_type.value, not c.eligible))
    _ = DECISION_OPTION_TAXONOMY_VERSION
    return candidates[:MAX_DECISION_OPTION_CANDIDATES]
