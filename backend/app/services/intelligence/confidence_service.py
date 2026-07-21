"""Confidence scoring — separate from readiness, penalized by weak source data."""

from app.domain.enums import ConfidenceLevel, CoverageLevel, RiskFindingType
from app.domain.models import CoverageResult, RiskFinding, TeamComposition
from app.domain.policy import get_policy
from app.services.intelligence.decision_trace_service import DecisionTraceService


class ConfidenceService:
    def score(
        self,
        coverage_results: list[CoverageResult],
        risk_findings: list[RiskFinding],
        team: TeamComposition,
        trace: DecisionTraceService,
        policy_version: str | None = None,
    ) -> tuple[int, ConfidenceLevel]:
        policy = get_policy(policy_version)
        raw = float(policy.CONFIDENCE_BASE)
        trace.add(
            step="confidence",
            component="base",
            label="confidence_base",
            value=str(policy.CONFIDENCE_BASE),
            contribution=float(policy.CONFIDENCE_BASE),
        )

        if not team.engineers:
            raw -= policy.CONFIDENCE_EMPTY_TEAM_PENALTY
            trace.add(
                step="confidence",
                component="team",
                label="empty_team",
                value="no engineers",
                contribution=-policy.CONFIDENCE_EMPTY_TEAM_PENALTY,
            )
        else:
            for engineer in team.engineers:
                if not engineer.has_certifications:
                    raw -= policy.CONFIDENCE_NO_CERTIFICATIONS_PENALTY
                    trace.add(
                        step="confidence",
                        component="evidence",
                        label=f"{engineer.id}_no_certs",
                        value=engineer.name,
                        contribution=-policy.CONFIDENCE_NO_CERTIFICATIONS_PENALTY,
                    )
                if not engineer.has_project_history:
                    raw -= policy.CONFIDENCE_NO_PROJECTS_PENALTY
                    trace.add(
                        step="confidence",
                        component="evidence",
                        label=f"{engineer.id}_no_projects",
                        value=engineer.name,
                        contribution=-policy.CONFIDENCE_NO_PROJECTS_PENALTY,
                    )

        for result in coverage_results:
            if result.is_critical and result.level == CoverageLevel.MISSING:
                raw -= policy.CONFIDENCE_MISSING_CRITICAL_PENALTY
                trace.add(
                    step="confidence",
                    component="coverage",
                    label=f"{result.capability_id}_missing_critical",
                    value=result.capability_name,
                    contribution=-policy.CONFIDENCE_MISSING_CRITICAL_PENALTY,
                )
            elif result.is_critical and result.level == CoverageLevel.WEAK:
                raw -= policy.CONFIDENCE_WEAK_CRITICAL_PENALTY
                trace.add(
                    step="confidence",
                    component="coverage",
                    label=f"{result.capability_id}_weak_critical",
                    value=result.capability_name,
                    contribution=-policy.CONFIDENCE_WEAK_CRITICAL_PENALTY,
                )

        for finding in risk_findings:
            if finding.finding_type == RiskFindingType.KEY_PERSON_DEPENDENCY:
                raw -= policy.CONFIDENCE_KEY_PERSON_PENALTY
                trace.add(
                    step="confidence",
                    component="risk",
                    label="key_person_dependency",
                    value=finding.capability_id or "unknown",
                    contribution=-policy.CONFIDENCE_KEY_PERSON_PENALTY,
                )
            elif finding.finding_type == RiskFindingType.DUPLICATE_TEAM_MEMBER:
                raw -= policy.CONFIDENCE_DUPLICATE_MEMBER_PENALTY
                trace.add(
                    step="confidence",
                    component="team",
                    label="duplicate_member",
                    value=finding.engineer_id or "unknown",
                    contribution=-policy.CONFIDENCE_DUPLICATE_MEMBER_PENALTY,
                )
            elif finding.finding_type == RiskFindingType.INCOMPLETE_EVIDENCE:
                raw -= policy.CONFIDENCE_INCOMPLETE_EVIDENCE_PENALTY
                trace.add(
                    step="confidence",
                    component="evidence",
                    label="incomplete_evidence",
                    value=finding.engineer_id or "unknown",
                    contribution=-policy.CONFIDENCE_INCOMPLETE_EVIDENCE_PENALTY,
                )

        clamped, delta = trace.reconcile_to_score(raw)
        if delta != 0:
            trace.add(
                step="confidence",
                component="normalization",
                label="score_clamp",
                value=f"raw={raw:.2f}",
                contribution=round(delta, 4),
            )

        level = self._level_for_score(clamped, policy)
        return clamped, level

    def _level_for_score(self, score: int, policy) -> ConfidenceLevel:
        if score >= policy.CONFIDENCE_LEVEL_HIGH_MIN:
            return ConfidenceLevel.HIGH
        if score >= policy.CONFIDENCE_LEVEL_MEDIUM_MIN:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
