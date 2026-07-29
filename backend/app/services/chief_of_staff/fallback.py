"""Deterministic fallback Chief of Staff brief builder."""

from __future__ import annotations

import hashlib

from app.domain.chief_of_staff_constants import (
    FALLBACK_TEMPLATE_VERSION,
    MAX_CLAIMS,
    OUTPUT_SCHEMA_VERSION,
)
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffClaimAuthorship,
    ChiefOfStaffClaimSupportStatus,
    ChiefOfStaffClaimType,
    ChiefOfStaffGenerationState,
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffSection,
    EvidenceEntryType,
)
from app.domain.chief_of_staff_models import (
    ChiefOfStaffBrief,
    ChiefOfStaffBriefSectionContent,
    ChiefOfStaffCitation,
    ChiefOfStaffClaim,
    ChiefOfStaffEvidencePackage,
)
from app.domain.prediction_enums import EstimateKind
from app.services.chief_of_staff.prompt_templates import PromptBundle
from app.services.chief_of_staff.provider_interface import CosProviderGenerationResult


def _claim_id(package_hash: str, index: int) -> str:
    material = f"{package_hash or 'pkg'}|{index}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"clm_{digest}"


def _citation_id(package_hash: str, claim_index: int, cite_index: int) -> str:
    material = f"{package_hash or 'pkg'}|{claim_index}|{cite_index}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"cit_{digest}"


class DeterministicFallbackProvider:
    def generate(
        self,
        *,
        evidence_package_json: str,
        prompt_bundle: PromptBundle,
    ) -> CosProviderGenerationResult:
        package = ChiefOfStaffEvidencePackage.model_validate_json(evidence_package_json)
        brief = build_fallback_brief(
            package,
            evidence_package_hash=package.package_hash,
            prompt_version=prompt_bundle.prompt_version,
        )
        return CosProviderGenerationResult(
            raw_content=brief.model_dump_json(),
            provider_mode=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
            metadata={
                "source": "deterministic_fallback",
                "fallback_template_version": FALLBACK_TEMPLATE_VERSION,
            },
        )


def build_fallback_brief(
    package: ChiefOfStaffEvidencePackage,
    *,
    evidence_package_hash: str | None = None,
    package_id: str | None = None,
    prompt_version: str = "",
) -> ChiefOfStaffBrief:
    """Build deterministic fallback brief.

    Citations bind to the content-canonical evidence package hash. ``package_id``
    remains as a deprecated alias for that hash (not a DB snapshot PK).
    """
    _ = prompt_version
    package_ref = evidence_package_hash or package_id or package.package_hash
    if not package_ref:
        raise ValueError("evidence_package_hash is required for fallback brief")
    claims: list[ChiefOfStaffClaim] = []
    citations: list[ChiefOfStaffCitation] = []
    sections: list[ChiefOfStaffBriefSectionContent] = []
    as_of = package.as_of_at
    package_hash = package.package_hash or package_ref
    evidence_by_type: dict[EvidenceEntryType, list] = {}
    for entry in package.evidence_entries:
        evidence_by_type.setdefault(entry.evidence_type, []).append(entry)

    def add_claim(
        claim_type: ChiefOfStaffClaimType,
        text: str,
        evidence_ids: list[str],
        *,
        semantic: dict | None = None,
    ) -> str:
        if len(claims) >= MAX_CLAIMS:
            return ""
        idx = len(claims)
        cid = _claim_id(package_hash, idx)
        safe_ids = evidence_ids[:5]
        claims.append(
            ChiefOfStaffClaim(
                claim_id=cid,
                claim_type=claim_type,
                text=text[:1000],
                support_status=ChiefOfStaffClaimSupportStatus.SUPPORTED,
                authorship=ChiefOfStaffClaimAuthorship.DETERMINISTIC,
                temporal_cutoff=as_of,
                evidence_ids=safe_ids,
                semantic_metadata=semantic or {},
                ordering_index=idx,
            )
        )
        for cite_i, eid in enumerate(safe_ids):
            entry = next(e for e in package.evidence_entries if e.evidence_id == eid)
            citations.append(
                ChiefOfStaffCitation(
                    citation_id=_citation_id(package_hash, idx, cite_i),
                    claim_id=cid,
                    evidence_id=eid,
                    evidence_type=entry.evidence_type,
                    package_id=package_ref,
                    ordering_index=cite_i,
                )
            )
        return cid

    target_ids = [e.evidence_id for e in evidence_by_type.get(EvidenceEntryType.TARGET_METADATA, [])]
    risk_ids = [e.evidence_id for e in package.deterministic_risks]
    finding_ids = [e.evidence_id for e in package.graph_findings]
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
    package_ids = [
        e.evidence_id
        for e in package.evidence_entries
        if e.evidence_type == EvidenceEntryType.PACKAGE_METADATA
    ]
    pred_ids = [package.prediction_evidence_id] if package.prediction_evidence_id else []
    scenario_ids = [
        e.evidence_id
        for e in package.evidence_entries
        if e.evidence_type
        in {
            EvidenceEntryType.SCENARIO_RUN,
            EvidenceEntryType.SCENARIO_RESULT,
            EvidenceEntryType.SCENARIO_IMPACT,
        }
    ]
    change_ids = [
        e.evidence_id
        for e in package.evidence_entries
        if e.evidence_type == EvidenceEntryType.DETERMINISTIC_CHANGE
    ]

    if target_ids:
        summary_claim = add_claim(
            ChiefOfStaffClaimType.SOURCE_FACT,
            (
                f"Delivery posture brief for {package.target_lifecycle.display_name} "
                f"({package.target_type.value}) as of {as_of.isoformat()}."
            ),
            target_ids,
        )
    else:
        # Never cite package_metadata as a SOURCE_FACT (support-matrix incompatible).
        summary_claim = add_claim(
            ChiefOfStaffClaimType.LIMITATION,
            (
                f"Delivery posture brief for {package.target_lifecycle.display_name} "
                f"({package.target_type.value}) as of {as_of.isoformat()}; "
                f"target metadata evidence unavailable."
            ),
            (package_ids or gap_ids)[:5] or [
                e.evidence_id for e in package.evidence_entries[:1]
            ],
        )

    posture_bits = []
    if package.deterministic_risks:
        posture_bits.append(f"{len(package.deterministic_risks)} deterministic risks in package")
    if package.graph_findings:
        posture_bits.append(f"{len(package.graph_findings)} active graph findings")
    if package.missing_data_warnings:
        posture_bits.append("missing-data warnings present")
    posture_text = "; ".join(posture_bits) or "Limited deterministic posture evidence at cutoff"
    if risk_ids or finding_ids:
        posture_claim = add_claim(
            ChiefOfStaffClaimType.DETERMINISTIC_FINDING,
            posture_text,
            (risk_ids + finding_ids)[:5],
        )
    elif target_ids:
        posture_claim = add_claim(
            ChiefOfStaffClaimType.SOURCE_FACT,
            posture_text,
            target_ids[:5],
        )
    else:
        posture_claim = add_claim(
            ChiefOfStaffClaimType.LIMITATION,
            posture_text,
            package_ids[:5],
        )

    risk_claim_ids = []
    for risk in package.deterministic_risks[:5]:
        risk_claim_ids.append(
            add_claim(
                ChiefOfStaffClaimType.DETERMINISTIC_FINDING,
                risk.summary,
                [risk.evidence_id],
            )
        )

    change_claim_ids = []
    if package.intent == ChiefOfStaffIntent.CHANGE_SINCE_LAST_REVIEW:
        for change in package.deterministic_changes[:10]:
            evid = [
                eid
                for eid in (change.current_evidence_id, change.prior_evidence_id)
                if eid
            ]
            change_entry_ids = change_ids[:1] + evid
            # Prefer deterministic_change entries.
            preferred = [
                e.evidence_id
                for e in package.evidence_entries
                if e.evidence_type == EvidenceEntryType.DETERMINISTIC_CHANGE
                and change.change_id in e.source_record_id
            ]
            change_claim_ids.append(
                add_claim(
                    ChiefOfStaffClaimType.DETERMINISTIC_CHANGE,
                    change.summary,
                    (preferred or change_entry_ids or package_ids)[:5],
                )
            )

    estimate_kind = package.prediction.estimate_kind if package.prediction else None
    probability = package.prediction.probability if package.prediction else None
    uncalibrated = package.prediction.uncalibrated_score if package.prediction else None
    estimate_claim = ""
    if package.prediction and pred_ids:
        if estimate_kind == EstimateKind.UNCALIBRATED_SCORE:
            estimate_text = (
                f"Delivery estimate kind is uncalibrated_score "
                f"(score={uncalibrated}); probability is unavailable. "
                "This is decision support only and not a delivery guarantee."
            )
            probability = None
        elif estimate_kind == EstimateKind.CALIBRATED_PROBABILITY:
            estimate_text = (
                f"Calibrated delivery probability={probability} from an active validated model."
            )
        else:
            estimate_text = "Insufficient prediction data at cutoff."
        if package.prediction.notes:
            estimate_text += " " + " ".join(package.prediction.notes)
        estimate_claim = add_claim(
            ChiefOfStaffClaimType.PREDICTION_ESTIMATE,
            estimate_text,
            pred_ids,
            semantic={"estimate_kind": estimate_kind.value if estimate_kind else None},
        )

    scenario_claim = ""
    if package.scenario_runs or package.scenario_impacts:
        if package.scenario_comparability and not package.scenario_comparability.comparable:
            scenario_text = (
                f"Scenario comparison limited: {package.scenario_comparability.reason}. "
                "Numeric estimate delta is not communicated across differing estimate kinds."
            )
        else:
            scenario_text = (
                f"{len(package.scenario_runs)} scenario run evidence items and "
                f"{len(package.scenario_impacts)} impacts included. "
                "Scenario outputs are counterfactual decision support and do not establish causation."
            )
        scenario_claim = add_claim(
            ChiefOfStaffClaimType.SCENARIO_IMPLICATION,
            scenario_text,
            (scenario_ids or package_ids)[:5],
        )

    gap_claim = add_claim(
        ChiefOfStaffClaimType.EVIDENCE_GAP,
        (
            f"Freshness={package.freshness_summary.overall_state}; "
            f"missing={len(package.missing_data_warnings)}; "
            f"truncated={package.truncation.any_truncated}."
        ),
        (gap_ids or package_ids)[:5],
    )

    limitation_claim = add_claim(
        ChiefOfStaffClaimType.LIMITATION,
        (
            "Deterministic fallback brief. Tenant header is not authentication. "
            "No autonomous decisions. Synthetic/demo scope may apply. "
            f"fallback_template={FALLBACK_TEMPLATE_VERSION}."
        ),
        (package_ids or gap_ids)[:5],
    )

    decision_types = []
    option_claim_ids = []
    for opt in package.decision_option_candidates:
        if not opt.eligible:
            continue
        decision_types.append(opt.option_type)
        option_claim_ids.append(
            add_claim(
                ChiefOfStaffClaimType.ADVISORY_OPTION,
                f"Advisory option: {opt.option_type.value}. {opt.rationale}",
                (opt.supporting_evidence_ids or package_ids)[:5],
                semantic={"option_type": opt.option_type.value, "advisory": True},
            )
        )

    def section(sec: ChiefOfStaffSection, text: str, claim_ids: list[str]) -> None:
        sections.append(
            ChiefOfStaffBriefSectionContent(
                section=sec,
                text=text[:4000],
                claim_ids=[c for c in claim_ids if c],
            )
        )

    section(
        ChiefOfStaffSection.EXECUTIVE_SUMMARY,
        f"Fallback executive summary for intent={package.intent.value}.",
        [summary_claim, posture_claim],
    )
    section(ChiefOfStaffSection.CURRENT_POSTURE, posture_text, [posture_claim])
    if change_claim_ids:
        section(
            ChiefOfStaffSection.MATERIAL_CHANGES,
            "Deterministic additions/removals/material changes since prior brief.",
            change_claim_ids,
        )
    if risk_claim_ids:
        section(
            ChiefOfStaffSection.TOP_DELIVERY_RISKS,
            "Top deterministic delivery risks from package evidence.",
            risk_claim_ids,
        )
    if scenario_claim:
        section(
            ChiefOfStaffSection.SCENARIO_IMPLICATIONS,
            "Scenario implications from completed runs.",
            [scenario_claim],
        )
    if estimate_claim:
        section(
            ChiefOfStaffSection.ESTIMATE_INTERPRETATION,
            "Estimate interpretation preserving estimate_kind semantics.",
            [estimate_claim],
        )
    section(
        ChiefOfStaffSection.DECISION_OPTIONS,
        "Allowlisted advisory decision options only; no autonomous execution.",
        option_claim_ids,
    )
    section(
        ChiefOfStaffSection.EVIDENCE_GAPS,
        "Evidence gaps, freshness, and truncation limitations.",
        [gap_claim],
    )
    section(
        ChiefOfStaffSection.QUESTIONS_FOR_LEADERSHIP,
        (
            "Which missing evidence should be prioritized? "
            "Which advisory option warrants human review?"
        ),
        [gap_claim, limitation_claim],
    )
    section(
        ChiefOfStaffSection.LIMITATIONS,
        "Fallback limitations and responsible-use constraints.",
        [limitation_claim],
    )
    section(
        ChiefOfStaffSection.PROVIDER_PROVENANCE,
        (
            f"final_provider=deterministic_fallback; "
            f"template={FALLBACK_TEMPLATE_VERSION}; "
            f"output_schema={OUTPUT_SCHEMA_VERSION}."
        ),
        [limitation_claim],
    )
    section(
        ChiefOfStaffSection.FALLBACK_VISIBILITY,
        "This brief was produced by deterministic fallback and is explicitly marked.",
        [limitation_claim],
    )

    limitations = [
        "Deterministic fallback used",
        "Decision options are advisory only",
        "No delivery guarantee",
        "No autonomous actions",
    ]
    if package.truncation.any_truncated:
        limitations.append("Evidence package truncated under bounded limits")
    if estimate_kind == EstimateKind.UNCALIBRATED_SCORE:
        limitations.append("Uncalibrated score is not a probability")

    return ChiefOfStaffBrief(
        schema_version=OUTPUT_SCHEMA_VERSION,
        intent=package.intent,
        target_type=package.target_type,
        target_id=package.target_id,
        as_of_at=as_of,
        horizon_days=package.horizon_days,
        sections=sections,
        claims=claims,
        citations=citations,
        decision_option_types=decision_types,
        estimate_kind=estimate_kind,
        probability=probability,
        uncalibrated_score=uncalibrated,
        provider_mode=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        generation_state=ChiefOfStaffGenerationState.FALLBACK_GENERATED,
        fallback_visible=True,
        limitations=limitations,
        synthetic_demo_scope=any(
            "synthetic" in n.lower() or "demo" in n.lower()
            for n in (package.prediction.notes if package.prediction else [])
        )
        or package.tenant_id == "novabank",
    )
