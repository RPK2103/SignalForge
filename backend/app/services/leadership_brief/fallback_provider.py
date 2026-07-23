"""Deterministic fallback Leadership Brief provider."""

from __future__ import annotations

import json

from app.domain.enums import RiskFindingType, RiskSeverity
from app.domain.leadership_brief_models import (
    GenerationStatus,
    LeadershipActionPriority,
    LeadershipBrief,
    LeadershipBriefAction,
    LeadershipBriefEvidencePackage,
    LeadershipBriefRisk,
    LeadershipBriefRiskSeverity,
    ProviderMode,
)
from app.services.leadership_brief.policy_v1 import (
    MAX_MITIGATION_ACTIONS,
    MAX_STAFFING_ACTIONS,
    MAX_TOP_RISKS,
    map_leadership_decision,
    severity_rank,
)
from app.services.leadership_brief.prompt_templates import PROMPT_VERSION, PromptBundle
from app.services.leadership_brief.provider_interface import ProviderGenerationResult


class DeterministicFallbackProvider:
    def generate(
        self,
        *,
        evidence_package_json: str,
        prompt_bundle: PromptBundle,
    ) -> ProviderGenerationResult:
        package = LeadershipBriefEvidencePackage.model_validate_json(evidence_package_json)
        brief = self.build_brief(package, prompt_version=prompt_bundle.prompt_version)
        return ProviderGenerationResult(
            raw_content=brief.model_dump_json(),
            provider_mode=ProviderMode.DETERMINISTIC_FALLBACK,
            metadata={"source": "deterministic_fallback"},
        )

    def build_brief(
        self,
        package: LeadershipBriefEvidencePackage,
        *,
        prompt_version: str = PROMPT_VERSION,
    ) -> LeadershipBrief:
        sorted_risks = sorted(
            package.risk_findings,
            key=lambda item: (severity_rank(item.severity), item.evidence_id),
        )
        top_risks: list[LeadershipBriefRisk] = []
        for finding in sorted_risks[:MAX_TOP_RISKS]:
            top_risks.append(
                LeadershipBriefRisk(
                    title=finding.message[:120],
                    explanation=finding.message,
                    severity=LeadershipBriefRiskSeverity(finding.severity),
                    evidence_references=[finding.evidence_id],
                )
            )

        staffing_actions: list[LeadershipBriefAction] = []
        mitigation_actions: list[LeadershipBriefAction] = []

        for finding in sorted_risks:
            if finding.finding_type == RiskFindingType.KEY_PERSON_DEPENDENCY.value:
                if len(staffing_actions) >= MAX_STAFFING_ACTIONS:
                    break
                engineer_ids = [finding.engineer_id] if finding.engineer_id else []
                staffing_actions.append(
                    LeadershipBriefAction(
                        title="Reduce key-person dependency",
                        action=(
                            "Establish secondary ownership and cross-training for the "
                            "critical engineer before execution approval."
                        ),
                        rationale=finding.message,
                        priority=LeadershipActionPriority.HIGH,
                        capability_id=finding.capability_id,
                        engineer_ids=engineer_ids,
                        evidence_references=[finding.evidence_id],
                    )
                )
            elif finding.finding_type in {
                RiskFindingType.MISSING_CRITICAL_CAPABILITY.value,
                RiskFindingType.WEAK_CAPABILITY.value,
            }:
                if len(mitigation_actions) >= MAX_MITIGATION_ACTIONS:
                    break
                priority = (
                    LeadershipActionPriority.CRITICAL
                    if finding.severity == RiskSeverity.HIGH.value
                    else LeadershipActionPriority.HIGH
                )
                mitigation_actions.append(
                    LeadershipBriefAction(
                        title=f"Address capability risk: {finding.capability_id or 'team'}",
                        action=(
                            "Staff or strengthen coverage for the affected capability before "
                            "committing to delivery."
                        ),
                        rationale=finding.message,
                        priority=priority,
                        capability_id=finding.capability_id,
                        engineer_ids=[finding.engineer_id] if finding.engineer_id else [],
                        evidence_references=[finding.evidence_id],
                    )
                )

        for gap in sorted(package.skill_gaps, key=lambda item: item.get("capability_id", "")):
            if len(mitigation_actions) >= MAX_MITIGATION_ACTIONS:
                break
            capability_id = gap.get("capability_id")
            matching = next(
                (item for item in package.risk_findings if item.capability_id == capability_id),
                None,
            )
            evidence_refs = [matching.evidence_id] if matching else []
            if not evidence_refs:
                trace = next(
                    (
                        item
                        for item in package.decision_trace
                        if capability_id and capability_id in item.label
                    ),
                    None,
                )
                if trace:
                    evidence_refs = [trace.evidence_id]
            if not evidence_refs:
                continue
            mitigation_actions.append(
                LeadershipBriefAction(
                    title=f"Close skill gap for {gap.get('capability_name', capability_id)}",
                    action="Assign targeted upskilling or add a specialist to close the identified gap.",
                    rationale=(
                        f"Deterministic assessment identified a {gap.get('level')} gap for "
                        f"{gap.get('capability_name', capability_id)}."
                    ),
                    priority=(
                        LeadershipActionPriority.CRITICAL
                        if gap.get("is_critical")
                        else LeadershipActionPriority.MEDIUM
                    ),
                    capability_id=capability_id,
                    engineer_ids=[],
                    evidence_references=evidence_refs,
                )
            )

        has_high_risk = any(
            item.severity == RiskSeverity.HIGH.value for item in package.risk_findings
        )
        has_critical_gap = any(item.get("is_critical") for item in package.skill_gaps)
        has_key_person = any(
            item.finding_type == RiskFindingType.KEY_PERSON_DEPENDENCY.value
            for item in package.risk_findings
        )
        decision = map_leadership_decision(
            readiness_score=package.readiness_score,
            confidence_score=package.confidence_score,
            has_high_risk=has_high_risk,
            has_critical_gap=has_critical_gap,
            has_key_person_dependency=has_key_person,
        )

        confidence_statement = (
            f"Leadership should treat this assessment with {package.confidence_level} "
            f"confidence ({package.confidence_score}/100) based on deterministic evidence "
            f"quality and coverage completeness."
        )
        executive_summary = (
            f"Project '{package.project_name}' readiness is {package.readiness_score}/100 with "
            f"{package.confidence_level} confidence. "
            f"Recommended leadership decision: {decision.value.replace('_', ' ')}. "
            f"{package.deterministic_summary}"
        )

        nested_refs = sorted(
            {
                ref
                for risk in top_risks
                for ref in risk.evidence_references
            }
            | {
                ref
                for action in staffing_actions + mitigation_actions
                for ref in action.evidence_references
            }
        )

        return LeadershipBrief(
            executive_summary=executive_summary,
            decision=decision,
            top_risks=top_risks,
            staffing_actions=_dedupe_actions(staffing_actions)[:MAX_STAFFING_ACTIONS],
            mitigation_actions=_dedupe_actions(mitigation_actions)[:MAX_MITIGATION_ACTIONS],
            confidence_statement=confidence_statement,
            evidence_references=nested_refs,
            provider_mode=ProviderMode.DETERMINISTIC_FALLBACK,
            prompt_version=prompt_version,
            generation_status=GenerationStatus.FALLBACK_GENERATED,
        )


def _dedupe_actions(actions: list[LeadershipBriefAction]) -> list[LeadershipBriefAction]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[LeadershipBriefAction] = []
    for action in actions:
        key = (action.title, action.action, action.priority.value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped
