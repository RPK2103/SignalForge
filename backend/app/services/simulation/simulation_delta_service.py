"""Deterministic delta calculation between baseline and proposed assessments."""

from app.domain.enums import CoverageLevel, RiskSeverity, SimulationChangeType
from app.domain.models import ReadinessAssessmentResponse
from app.domain.simulation_models import (
    CapabilityCoverageChange,
    DecisionTraceDelta,
    KeyPersonDependencyChange,
    RiskFindingChange,
    risk_finding_key,
    skill_gap_key,
    trace_entry_key,
)

_SEVERITY_RANK = {
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
}


class SimulationDeltaService:
    def compare(
        self,
        baseline: ReadinessAssessmentResponse,
        proposed: ReadinessAssessmentResponse,
    ) -> dict:
        readiness_delta = proposed.readiness_score - baseline.readiness_score
        confidence_delta = proposed.confidence_score - baseline.confidence_score

        return {
            "readiness_score_delta": readiness_delta,
            "confidence_delta": confidence_delta,
            "risk_level_changes": self._risk_changes(baseline, proposed),
            "capability_coverage_changes": self._coverage_changes(baseline, proposed),
            "newly_introduced_gaps": self._introduced_gaps(baseline, proposed),
            "resolved_gaps": self._resolved_gaps(baseline, proposed),
            "key_person_dependency_changes": self._dependency_changes(baseline, proposed),
            "decision_trace_delta": self._trace_delta(baseline, proposed),
        }

    def _risk_changes(
        self,
        baseline: ReadinessAssessmentResponse,
        proposed: ReadinessAssessmentResponse,
    ) -> list[RiskFindingChange]:
        baseline_map = {risk_finding_key(finding): finding for finding in baseline.risk_findings}
        proposed_map = {risk_finding_key(finding): finding for finding in proposed.risk_findings}

        changes: list[RiskFindingChange] = []
        for key, proposed_finding in proposed_map.items():
            baseline_finding = baseline_map.get(key)
            if baseline_finding is None:
                changes.append(
                    RiskFindingChange(
                        change_type=SimulationChangeType.INTRODUCED,
                        finding_type=proposed_finding.finding_type,
                        severity=proposed_finding.severity,
                        proposed_severity=proposed_finding.severity,
                        capability_id=proposed_finding.capability_id,
                        engineer_id=proposed_finding.engineer_id,
                        message=proposed_finding.message,
                    )
                )
                continue

            baseline_rank = _SEVERITY_RANK[baseline_finding.severity]
            proposed_rank = _SEVERITY_RANK[proposed_finding.severity]
            if proposed_rank > baseline_rank:
                change_type = SimulationChangeType.ESCALATED
            elif proposed_rank < baseline_rank:
                change_type = SimulationChangeType.DEESCALATED
            elif proposed_finding.message != baseline_finding.message:
                change_type = SimulationChangeType.MODIFIED
            else:
                continue

            changes.append(
                RiskFindingChange(
                    change_type=change_type,
                    finding_type=proposed_finding.finding_type,
                    severity=proposed_finding.severity,
                    baseline_severity=baseline_finding.severity,
                    proposed_severity=proposed_finding.severity,
                    capability_id=proposed_finding.capability_id,
                    engineer_id=proposed_finding.engineer_id,
                    message=proposed_finding.message,
                )
            )

        for key, baseline_finding in baseline_map.items():
            if key not in proposed_map:
                changes.append(
                    RiskFindingChange(
                        change_type=SimulationChangeType.RESOLVED,
                        finding_type=baseline_finding.finding_type,
                        severity=baseline_finding.severity,
                        baseline_severity=baseline_finding.severity,
                        capability_id=baseline_finding.capability_id,
                        engineer_id=baseline_finding.engineer_id,
                        message=baseline_finding.message,
                    )
                )

        return sorted(
            changes,
            key=lambda item: (
                item.change_type.value,
                item.finding_type.value,
                item.capability_id or "",
                item.engineer_id or "",
            ),
        )

    def _coverage_changes(
        self,
        baseline: ReadinessAssessmentResponse,
        proposed: ReadinessAssessmentResponse,
    ) -> list[CapabilityCoverageChange]:
        baseline_map = {item.capability_id: item for item in baseline.coverage_results}
        proposed_map = {item.capability_id: item for item in proposed.coverage_results}
        changes: list[CapabilityCoverageChange] = []

        for capability_id in sorted(set(baseline_map) | set(proposed_map)):
            baseline_item = baseline_map.get(capability_id)
            proposed_item = proposed_map.get(capability_id)
            if baseline_item is None or proposed_item is None:
                continue
            if (
                baseline_item.level == proposed_item.level
                and baseline_item.team_proficiency == proposed_item.team_proficiency
                and baseline_item.covering_engineer_ids == proposed_item.covering_engineer_ids
            ):
                continue

            score_delta = proposed_item.team_proficiency - baseline_item.team_proficiency
            if score_delta > 0:
                change_type = SimulationChangeType.IMPROVED
            elif score_delta < 0:
                change_type = SimulationChangeType.DEGRADED
            else:
                change_type = SimulationChangeType.MODIFIED

            affected = sorted(
                set(baseline_item.covering_engineer_ids) ^ set(proposed_item.covering_engineer_ids)
            )
            changes.append(
                CapabilityCoverageChange(
                    change_type=change_type,
                    capability_id=capability_id,
                    capability_name=proposed_item.capability_name,
                    baseline_level=baseline_item.level,
                    proposed_level=proposed_item.level,
                    baseline_effective_score=baseline_item.team_proficiency,
                    proposed_effective_score=proposed_item.team_proficiency,
                    score_delta=score_delta,
                    affected_engineer_ids=affected,
                    is_critical=proposed_item.is_critical,
                )
            )

        return changes

    def _introduced_gaps(
        self,
        baseline: ReadinessAssessmentResponse,
        proposed: ReadinessAssessmentResponse,
    ) -> list:
        baseline_keys = {skill_gap_key(gap) for gap in baseline.skill_gaps}
        return sorted(
            [gap for gap in proposed.skill_gaps if skill_gap_key(gap) not in baseline_keys],
            key=lambda gap: (gap.capability_id, gap.level.value),
        )

    def _resolved_gaps(
        self,
        baseline: ReadinessAssessmentResponse,
        proposed: ReadinessAssessmentResponse,
    ) -> list:
        proposed_keys = {skill_gap_key(gap) for gap in proposed.skill_gaps}
        return sorted(
            [gap for gap in baseline.skill_gaps if skill_gap_key(gap) not in proposed_keys],
            key=lambda gap: (gap.capability_id, gap.level.value),
        )

    def _dependency_changes(
        self,
        baseline: ReadinessAssessmentResponse,
        proposed: ReadinessAssessmentResponse,
    ) -> list[KeyPersonDependencyChange]:
        changes: list[KeyPersonDependencyChange] = []
        baseline_map = {item.capability_id: item for item in baseline.coverage_results}
        proposed_map = {item.capability_id: item for item in proposed.coverage_results}

        for capability_id in sorted(set(baseline_map) | set(proposed_map)):
            baseline_item = baseline_map.get(capability_id)
            proposed_item = proposed_map.get(capability_id)
            if baseline_item is None or proposed_item is None:
                continue

            baseline_dependency = (
                len(baseline_item.covering_engineer_ids) == 1
                and baseline_item.level != CoverageLevel.MISSING
            )
            proposed_dependency = (
                len(proposed_item.covering_engineer_ids) == 1
                and proposed_item.level != CoverageLevel.MISSING
            )
            if (
                baseline_dependency == proposed_dependency
                and baseline_item.covering_engineer_ids == proposed_item.covering_engineer_ids
            ):
                continue

            if not baseline_dependency and proposed_dependency:
                change_type = SimulationChangeType.INTRODUCED
            elif baseline_dependency and not proposed_dependency:
                change_type = SimulationChangeType.RESOLVED
            else:
                change_type = SimulationChangeType.MODIFIED

            changes.append(
                KeyPersonDependencyChange(
                    change_type=change_type,
                    capability_id=capability_id,
                    capability_name=proposed_item.capability_name,
                    baseline_covering_engineer_ids=sorted(baseline_item.covering_engineer_ids),
                    proposed_covering_engineer_ids=sorted(proposed_item.covering_engineer_ids),
                    baseline_is_dependency=baseline_dependency,
                    proposed_is_dependency=proposed_dependency,
                    is_critical=proposed_item.is_critical,
                )
            )

        return changes

    def _trace_delta(
        self,
        baseline: ReadinessAssessmentResponse,
        proposed: ReadinessAssessmentResponse,
    ) -> list[DecisionTraceDelta]:
        baseline_map = {trace_entry_key(entry): entry for entry in baseline.decision_trace}
        proposed_map = {trace_entry_key(entry): entry for entry in proposed.decision_trace}
        deltas: list[DecisionTraceDelta] = []

        for key in sorted(set(baseline_map) | set(proposed_map)):
            baseline_entry = baseline_map.get(key)
            proposed_entry = proposed_map.get(key)
            baseline_contribution = baseline_entry.contribution if baseline_entry else 0.0
            proposed_contribution = proposed_entry.contribution if proposed_entry else 0.0
            if baseline_contribution == proposed_contribution:
                continue

            step, component, label = key
            deltas.append(
                DecisionTraceDelta(
                    trace_key=f"{step}:{component}:{label}",
                    step=step,
                    component=component,
                    label=label,
                    baseline_contribution=baseline_contribution,
                    proposed_contribution=proposed_contribution,
                    contribution_delta=proposed_contribution - baseline_contribution,
                    baseline_value=baseline_entry.value if baseline_entry else "",
                    proposed_value=proposed_entry.value if proposed_entry else "",
                )
            )

        deltas.extend(
            self._reconciliation_entries(
                step="readiness",
                baseline=baseline,
                proposed=proposed,
                score_delta=proposed.readiness_score - baseline.readiness_score,
                existing=deltas,
            )
        )
        deltas.extend(
            self._reconciliation_entries(
                step="confidence",
                baseline=baseline,
                proposed=proposed,
                score_delta=proposed.confidence_score - baseline.confidence_score,
                existing=deltas,
            )
        )
        return deltas

    def _reconciliation_entries(
        self,
        *,
        step: str,
        baseline: ReadinessAssessmentResponse,
        proposed: ReadinessAssessmentResponse,
        score_delta: int,
        existing: list[DecisionTraceDelta],
    ) -> list[DecisionTraceDelta]:
        structural_delta = sum(entry.contribution_delta for entry in existing if entry.step == step)
        gap = round(score_delta - structural_delta, 4)
        if gap == 0:
            return []

        return [
            DecisionTraceDelta(
                trace_key=f"{step}:reconciliation:score_boundary",
                step=step,
                component="reconciliation",
                label="Score boundary and rounding adjustment",
                baseline_contribution=0.0,
                proposed_contribution=gap,
                contribution_delta=gap,
                baseline_value=str(
                    baseline.readiness_score if step == "readiness" else baseline.confidence_score
                ),
                proposed_value=str(
                    proposed.readiness_score if step == "readiness" else proposed.confidence_score
                ),
            )
        ]
