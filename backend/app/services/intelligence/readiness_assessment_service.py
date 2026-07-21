"""Orchestrates the full readiness assessment pipeline."""

from app.domain.enums import CoverageLevel, RiskFindingType, RiskSeverity
from app.domain.evidence import deduplicate_team
from app.domain.models import (
    ReadinessAssessmentRequest,
    ReadinessAssessmentResponse,
    RiskFinding,
    TeamComposition,
)
from app.domain.policy import get_policy
from app.services.intelligence.capability_coverage_service import CapabilityCoverageService
from app.services.intelligence.confidence_service import ConfidenceService
from app.services.intelligence.decision_trace_service import DecisionTraceService
from app.services.intelligence.key_person_risk_service import KeyPersonRiskService
from app.services.intelligence.readiness_scoring_service import ReadinessScoringService
from app.services.intelligence.skill_gap_service import SkillGapService


class ReadinessAssessmentService:
    def __init__(self) -> None:
        self._coverage_service = CapabilityCoverageService()
        self._skill_gap_service = SkillGapService()
        self._key_person_service = KeyPersonRiskService()
        self._readiness_scoring_service = ReadinessScoringService()
        self._confidence_service = ConfidenceService()

    def assess(self, request: ReadinessAssessmentRequest) -> ReadinessAssessmentResponse:
        policy = get_policy()
        trace = DecisionTraceService(policy.POLICY_VERSION)

        unique_engineers, duplicate_ids = deduplicate_team(request.team.engineers)
        team = TeamComposition(engineers=unique_engineers)

        coverage_results = self._coverage_service.analyze(request.project, team)
        skill_gaps = self._skill_gap_service.analyze(coverage_results)
        risk_findings = self._key_person_service.analyze(coverage_results, team)

        for dup_id in duplicate_ids:
            risk_findings.append(
                RiskFinding(
                    finding_type=RiskFindingType.DUPLICATE_TEAM_MEMBER,
                    severity=RiskSeverity.LOW,
                    engineer_id=dup_id,
                    message=f"Duplicate team member '{dup_id}' was deduplicated.",
                )
            )

        readiness_score, dimension_scores = self._readiness_scoring_service.score(
            coverage_results=coverage_results,
            risk_findings=risk_findings,
            team=team,
            trace=trace,
        )
        confidence_score, confidence_level = self._confidence_service.score(
            coverage_results=coverage_results,
            risk_findings=risk_findings,
            team=team,
            trace=trace,
        )

        summary = self._build_summary(
            request.project.name,
            readiness_score,
            confidence_level.value,
            skill_gaps,
            coverage_results,
        )

        return ReadinessAssessmentResponse(
            project_id=request.project.id,
            project_name=request.project.name,
            readiness_score=readiness_score,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            coverage_results=coverage_results,
            skill_gaps=skill_gaps,
            risk_findings=risk_findings,
            dimension_scores=dimension_scores,
            decision_trace=trace.entries,
            policy_version=policy.POLICY_VERSION,
            summary=summary,
        )

    def _build_summary(
        self,
        project_name: str,
        readiness_score: int,
        confidence_level: str,
        skill_gaps,
        coverage_results,
    ) -> str:
        if not coverage_results:
            return (
                f"Project '{project_name}' has no capability requirements. "
                f"Readiness score {readiness_score}/100 with {confidence_level} confidence."
            )

        missing = [g.capability_name for g in skill_gaps if g.level == CoverageLevel.MISSING]
        weak = [g.capability_name for g in skill_gaps if g.level == CoverageLevel.WEAK]

        parts = [
            f"Project '{project_name}' readiness: {readiness_score}/100 "
            f"({confidence_level} confidence)."
        ]
        if missing:
            parts.append(f"Missing: {', '.join(missing)}.")
        if weak:
            parts.append(f"Weak: {', '.join(weak)}.")
        if not missing and not weak:
            parts.append("All required capabilities are adequately covered.")

        return " ".join(parts)
