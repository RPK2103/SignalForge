"""Grounding validation for Leadership Brief provider output."""

from __future__ import annotations

import re

from app.domain.leadership_brief_models import (
    LeadershipBrief,
    LeadershipBriefEvidencePackage,
    ProviderMode,
)


class GroundingValidationError(Exception):
    """Provider output failed evidence grounding checks."""


_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")


def _known_numeric_values(package: LeadershipBriefEvidencePackage) -> set[str]:
    values = {
        str(package.readiness_score),
        str(package.confidence_score),
    }
    for item in package.dimension_scores:
        if "score" in item:
            values.add(str(item["score"]))
        if "weight" in item:
            values.add(str(item["weight"]))
    for item in package.skill_gaps:
        if "covering_engineer_count" in item:
            values.add(str(item["covering_engineer_count"]))
        if "weight" in item:
            values.add(str(item["weight"]))
    for item in package.capability_coverage:
        if "team_proficiency" in item:
            values.add(str(item["team_proficiency"]))
        if "weight" in item:
            values.add(str(item["weight"]))
    for entry in package.decision_trace:
        values.add(str(entry.contribution))
        if entry.value.isdigit():
            values.add(entry.value)
    return values


def validate_grounding(
    brief: LeadershipBrief,
    package: LeadershipBriefEvidencePackage,
    *,
    expected_provider_mode: ProviderMode,
) -> None:
    if brief.provider_mode != expected_provider_mode:
        raise GroundingValidationError("provider mode mismatch")

    known_evidence = {item.evidence_id for item in package.risk_findings}
    known_evidence.update(item.evidence_id for item in package.decision_trace)
    known_capabilities = {
        item.get("capability_id")
        for item in package.skill_gaps + package.capability_coverage
        if item.get("capability_id")
    }
    known_capabilities.update(
        item.capability_id for item in package.risk_findings if item.capability_id
    )
    known_engineers = set(package.team_member_ids)
    known_engineers.update(item.engineer_id for item in package.risk_findings if item.engineer_id)

    nested_refs: list[str] = []
    for risk in brief.top_risks:
        if not risk.evidence_references:
            raise GroundingValidationError("risk missing evidence references")
        nested_refs.extend(risk.evidence_references)
        for ref in risk.evidence_references:
            if ref not in known_evidence:
                raise GroundingValidationError(f"unknown evidence reference: {ref}")

    for action in brief.staffing_actions + brief.mitigation_actions:
        if not action.evidence_references:
            raise GroundingValidationError("action missing evidence references")
        nested_refs.extend(action.evidence_references)
        for ref in action.evidence_references:
            if ref not in known_evidence:
                raise GroundingValidationError(f"unknown evidence reference: {ref}")
        if action.capability_id and action.capability_id not in known_capabilities:
            raise GroundingValidationError(f"unknown capability reference: {action.capability_id}")
        for engineer_id in action.engineer_ids:
            if engineer_id not in known_engineers:
                raise GroundingValidationError(f"unknown engineer reference: {engineer_id}")

    if sorted(set(brief.evidence_references)) != sorted(set(nested_refs)):
        raise GroundingValidationError("top-level evidence references mismatch")

    if len(brief.evidence_references) != len(set(brief.evidence_references)):
        raise GroundingValidationError("duplicate evidence references")

    known_numbers = _known_numeric_values(package)
    text_blob = " ".join(
        [
            brief.executive_summary,
            brief.confidence_statement,
            *[risk.title + " " + risk.explanation for risk in brief.top_risks],
            *[
                action.title + " " + action.action + " " + action.rationale
                for action in brief.staffing_actions + brief.mitigation_actions
            ],
        ]
    )
    for match in _NUMBER_PATTERN.findall(text_blob):
        if match not in known_numbers and int(float(match)) > 100:
            raise GroundingValidationError(f"unsupported numeric claim detected: {match}")
