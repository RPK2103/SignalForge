"""Claim support matrix and citation grounding validation."""

from __future__ import annotations

from app.domain.chief_of_staff_constants import MAX_CITATIONS_PER_CLAIM
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffClaimSupportStatus,
    ChiefOfStaffClaimType,
    EvidenceEntryType,
)
from app.domain.chief_of_staff_models import (
    ChiefOfStaffBrief,
    ChiefOfStaffEvidencePackage,
)
from app.domain.prediction_enums import EstimateKind

CLAIM_SUPPORT_MATRIX: dict[ChiefOfStaffClaimType, frozenset[EvidenceEntryType]] = {
    ChiefOfStaffClaimType.SOURCE_FACT: frozenset(
        {
            EvidenceEntryType.TARGET_METADATA,
            EvidenceEntryType.EVIDENCE_SIGNAL,
        }
    ),
    ChiefOfStaffClaimType.DETERMINISTIC_FINDING: frozenset(
        {
            EvidenceEntryType.ASSESSMENT_RISK,
            EvidenceEntryType.GRAPH_FINDING,
            EvidenceEntryType.READINESS_ASSESSMENT,
        }
    ),
    ChiefOfStaffClaimType.DETERMINISTIC_CHANGE: frozenset(
        {
            EvidenceEntryType.DETERMINISTIC_CHANGE,
            EvidenceEntryType.PRIOR_BRIEF_REFERENCE,
            EvidenceEntryType.ASSESSMENT_RISK,
            EvidenceEntryType.GRAPH_FINDING,
            EvidenceEntryType.EVIDENCE_SIGNAL,
        }
    ),
    ChiefOfStaffClaimType.PREDICTION_ESTIMATE: frozenset({EvidenceEntryType.DELIVERY_PREDICTION}),
    ChiefOfStaffClaimType.SCENARIO_IMPLICATION: frozenset(
        {
            EvidenceEntryType.SCENARIO_RUN,
            EvidenceEntryType.SCENARIO_RESULT,
            EvidenceEntryType.SCENARIO_IMPACT,
        }
    ),
    ChiefOfStaffClaimType.EVIDENCE_GAP: frozenset(
        {
            EvidenceEntryType.FRESHNESS_SUMMARY,
            EvidenceEntryType.MISSING_DATA_WARNING,
            EvidenceEntryType.TRUNCATION_METADATA,
            EvidenceEntryType.PACKAGE_METADATA,
        }
    ),
    ChiefOfStaffClaimType.LIMITATION: frozenset(
        {
            EvidenceEntryType.PACKAGE_METADATA,
            EvidenceEntryType.TRUNCATION_METADATA,
            EvidenceEntryType.PRIOR_BRIEF_REFERENCE,
            EvidenceEntryType.DELIVERY_PREDICTION,
        }
    ),
    ChiefOfStaffClaimType.ADVISORY_OPTION: frozenset(
        {
            EvidenceEntryType.DECISION_OPTION_CANDIDATE,
            EvidenceEntryType.ASSESSMENT_RISK,
            EvidenceEntryType.GRAPH_FINDING,
            EvidenceEntryType.MISSING_DATA_WARNING,
            EvidenceEntryType.FRESHNESS_SUMMARY,
            EvidenceEntryType.SCENARIO_RUN,
            EvidenceEntryType.PACKAGE_METADATA,
            EvidenceEntryType.TRUNCATION_METADATA,
            EvidenceEntryType.DELIVERY_PREDICTION,
            EvidenceEntryType.EVIDENCE_SIGNAL,
            EvidenceEntryType.TARGET_METADATA,
        }
    ),
}


class GroundingValidationError(ValueError):
    pass


class CitationValidationError(ValueError):
    pass


class UnsupportedClaimError(ValueError):
    pass


def validate_brief_grounding(
    brief: ChiefOfStaffBrief,
    package: ChiefOfStaffEvidencePackage,
    *,
    package_id: str | None = None,
    evidence_package_hash: str | None = None,
) -> None:
    """Validate claims/citations against the exact evidence package.

    ``evidence_package_hash`` (preferred) or ``package_id`` must equal the
    content-canonical ``package.package_hash``. Database snapshot primary keys
    are not accepted as semantic package identity.
    """
    expected_hash = evidence_package_hash or package_id or package.package_hash
    if not expected_hash:
        raise GroundingValidationError("evidence package hash required for grounding")
    if package.package_hash and expected_hash != package.package_hash:
        raise GroundingValidationError("evidence package hash mismatch")

    evidence_by_id = {e.evidence_id: e for e in package.evidence_entries}
    allowed_options = {c.option_type for c in package.decision_option_candidates if c.eligible}

    seen_claim_ids: set[str] = set()
    seen_citation_ids: set[str] = set()

    for claim in brief.claims:
        if claim.claim_id in seen_claim_ids:
            raise GroundingValidationError("duplicate claim_id")
        seen_claim_ids.add(claim.claim_id)

        if claim.support_status != ChiefOfStaffClaimSupportStatus.SUPPORTED:
            raise UnsupportedClaimError(f"Claim {claim.claim_id} is not fully supported")

        if not claim.evidence_ids:
            raise CitationValidationError(f"Claim {claim.claim_id} missing citations")

        if len(claim.evidence_ids) > MAX_CITATIONS_PER_CLAIM:
            raise CitationValidationError("citation count overflow")

        if len(claim.evidence_ids) != len(set(claim.evidence_ids)):
            raise CitationValidationError("duplicate evidence citation on claim")

        allowed_types = CLAIM_SUPPORT_MATRIX[claim.claim_type]
        for eid in claim.evidence_ids:
            entry = evidence_by_id.get(eid)
            if entry is None:
                raise CitationValidationError("citation references unknown evidence")
            if entry.tenant_id != package.tenant_id:
                raise CitationValidationError("foreign-tenant evidence citation")
            if entry.evidence_type not in allowed_types:
                raise CitationValidationError(
                    f"evidence type {entry.evidence_type.value} incompatible with "
                    f"claim type {claim.claim_type.value}"
                )
            # Temporal: source event must be at or before package cutoff when present.
            if entry.source_event_time is not None and entry.source_event_time > package.as_of_at:
                raise CitationValidationError("evidence not temporally valid at cutoff")

        if claim.claim_type == ChiefOfStaffClaimType.PREDICTION_ESTIMATE:
            if package.prediction is None:
                raise UnsupportedClaimError("prediction claim without prediction evidence")
            if brief.estimate_kind != package.prediction.estimate_kind:
                raise UnsupportedClaimError("estimate_kind mismatch")
            if (
                package.prediction.estimate_kind == EstimateKind.UNCALIBRATED_SCORE
                and brief.probability is not None
            ):
                raise UnsupportedClaimError("probability populated for uncalibrated score")

        if claim.claim_type == ChiefOfStaffClaimType.ADVISORY_OPTION:
            option = (claim.semantic_metadata or {}).get("option_type")
            if option is not None:
                from app.domain.chief_of_staff_enums import DecisionOptionType

                try:
                    opt = DecisionOptionType(option)
                except ValueError as exc:
                    raise UnsupportedClaimError("unknown decision option type") from exc
                if opt not in allowed_options:
                    raise UnsupportedClaimError("ineligible decision option")

    claim_ids = {c.claim_id for c in brief.claims}
    for citation in brief.citations:
        if citation.citation_id in seen_citation_ids:
            raise CitationValidationError("duplicate citation_id")
        seen_citation_ids.add(citation.citation_id)
        if citation.claim_id not in claim_ids:
            raise CitationValidationError("citation references unknown claim")
        if citation.package_id != expected_hash:
            raise CitationValidationError("citation outside exact package")
        entry = evidence_by_id.get(citation.evidence_id)
        if entry is None:
            raise CitationValidationError("fabricated evidence id")
        if entry.evidence_type != citation.evidence_type:
            raise CitationValidationError("citation evidence_type mismatch")

    # Every claim evidence_id must have a matching citation row.
    cited_pairs = {(c.claim_id, c.evidence_id) for c in brief.citations}
    for claim in brief.claims:
        for eid in claim.evidence_ids:
            if (claim.claim_id, eid) not in cited_pairs:
                raise CitationValidationError("missing citation row for claim evidence")

    # Decision options in brief must be subset of eligible allowlist.
    for opt in brief.decision_option_types:
        if opt not in allowed_options:
            raise UnsupportedClaimError("brief includes ineligible decision option")
