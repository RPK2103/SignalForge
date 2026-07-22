"""Deterministic readiness scoring with explicit weighted contributions."""

from app.domain.enums import CoverageLevel, ReadinessDimension
from app.domain.evidence import coverage_percentage
from app.domain.models import CoverageResult, ReadinessDimensionScore, RiskFinding, TeamComposition
from app.domain.policy import get_policy
from app.services.intelligence.decision_trace_service import DecisionTraceService


class ReadinessScoringService:
    def score(
        self,
        coverage_results: list[CoverageResult],
        risk_findings: list[RiskFinding],
        team: TeamComposition,
        trace: DecisionTraceService,
        policy_version: str | None = None,
    ) -> tuple[int, list[ReadinessDimensionScore]]:
        policy = get_policy(policy_version)

        if not team.engineers:
            trace.add(
                step="readiness",
                component="team",
                label="empty_team",
                value="0 engineers",
                contribution=0.0,
            )
            return 0, self._dimension_scores(0, 0, 0, 100, 0)

        weighted_total = sum(result.weight for result in coverage_results) or 1.0
        requirement_contributions = 0.0

        for result in coverage_results:
            multiplier = policy.LEVEL_MULTIPLIERS[result.level.value]
            contribution = (result.weight / weighted_total) * multiplier * 100
            requirement_contributions += contribution
            trace.add(
                step="coverage",
                component="requirement",
                label=result.capability_id,
                value=f"{result.level.value} (weight={result.weight})",
                contribution=round(contribution, 4),
            )

        coverage_pct = coverage_percentage(coverage_results)
        skill_depth = self._skill_depth_score(coverage_results)
        team_balance = self._team_balance_score(coverage_results, team)
        delivery_risk = self._delivery_risk_score(coverage_pct)
        evidence_quality = self._evidence_quality_score(team)

        dimension_scores = self._dimension_scores(
            coverage_pct,
            skill_depth,
            team_balance,
            delivery_risk,
            evidence_quality,
            policy_version,
        )

        weighted_readiness = sum(
            dim.score * dim.weight for dim in dimension_scores
        )

        for dim in dimension_scores:
            dim_contribution = dim.score * dim.weight
            trace.add(
                step="readiness",
                component="dimension",
                label=dim.dimension.value,
                value=f"score={dim.score}, weight={dim.weight}",
                contribution=round(dim_contribution, 4),
            )

        penalty = self._risk_penalty(risk_findings, trace, policy)
        raw_total = weighted_readiness - penalty
        final_score, delta = trace.reconcile_to_score(raw_total)

        if delta != 0:
            trace.add(
                step="readiness",
                component="normalization",
                label="score_clamp",
                value=f"raw={raw_total:.2f}",
                contribution=round(delta, 4),
            )

        return final_score, dimension_scores

    def _dimension_scores(
        self,
        coverage_pct: int,
        skill_depth: int,
        team_balance: int,
        delivery_risk: int,
        evidence_quality: int,
        policy_version: str | None = None,
    ) -> list[ReadinessDimensionScore]:
        policy = get_policy(policy_version)
        weights = policy.DIMENSION_WEIGHTS
        return [
            ReadinessDimensionScore(
                dimension=ReadinessDimension.CAPABILITY_COVERAGE,
                score=coverage_pct,
                weight=weights["capability_coverage"],
            ),
            ReadinessDimensionScore(
                dimension=ReadinessDimension.SKILL_DEPTH,
                score=skill_depth,
                weight=weights["skill_depth"],
            ),
            ReadinessDimensionScore(
                dimension=ReadinessDimension.TEAM_BALANCE,
                score=team_balance,
                weight=weights["team_balance"],
            ),
            ReadinessDimensionScore(
                dimension=ReadinessDimension.DELIVERY_RISK,
                score=delivery_risk,
                weight=weights["delivery_risk"],
            ),
            ReadinessDimensionScore(
                dimension=ReadinessDimension.EVIDENCE_QUALITY,
                score=evidence_quality,
                weight=weights["evidence_quality"],
            ),
        ]

    def _skill_depth_score(self, coverage_results: list[CoverageResult]) -> int:
        if not coverage_results:
            return 100
        proficiencies = [
            result.team_proficiency
            for result in coverage_results
            if result.level != CoverageLevel.MISSING
        ]
        if not proficiencies:
            return 0
        return round(sum(proficiencies) / len(proficiencies))

    def _team_balance_score(
        self,
        coverage_results: list[CoverageResult],
        team: TeamComposition,
    ) -> int:
        if not team.engineers:
            return 0
        single_person_count = sum(
            1
            for result in coverage_results
            if len(result.covering_engineer_ids) == 1 and result.level != CoverageLevel.MISSING
        )
        if not coverage_results:
            return 100
        dependency_ratio = single_person_count / len(coverage_results)
        return max(0, round(100 - dependency_ratio * 100))

    def _delivery_risk_score(self, coverage_pct: int) -> int:
        return max(0, min(100, coverage_pct))

    def _evidence_quality_score(self, team: TeamComposition) -> int:
        if not team.engineers:
            return 0
        scores: list[int] = []
        for engineer in team.engineers:
            score = 100
            if not engineer.has_certifications:
                score -= 25
            if not engineer.has_project_history:
                score -= 25
            if engineer.experience_years < get_policy().MIN_EXPERIENCE_YEARS_FOR_ADEQUATE:
                score -= 20
            scores.append(max(0, score))
        return round(sum(scores) / len(scores))

    def _risk_penalty(
        self,
        risk_findings: list[RiskFinding],
        trace: DecisionTraceService,
        policy,
    ) -> float:
        penalty = 0.0
        for finding in risk_findings:
            amount = 0.0
            if finding.finding_type.value == "duplicate_team_member":
                amount = policy.CONFIDENCE_DUPLICATE_MEMBER_PENALTY * 0.5
            elif finding.finding_type.value == "missing_critical_capability":
                amount = 15.0
            elif finding.finding_type.value == "key_person_dependency":
                amount = 8.0 if finding.severity.value == "medium" else 12.0

            if amount > 0:
                penalty += amount
                trace.add(
                    step="readiness",
                    component="risk_penalty",
                    label=finding.finding_type.value,
                    value=finding.message[:80],
                    contribution=-round(amount, 4),
                )
        return penalty
