"""Deterministic delivery risk scorecard (uncalibrated baseline)."""

from __future__ import annotations

from typing import Any, Mapping

from app.domain.prediction_constants import (
    BAND_HIGH_MAX,
    BAND_LOW_MAX,
    BAND_MODERATE_MAX,
    SCORECARD_VERSION,
)
from app.domain.prediction_enums import EstimateKind, RiskBand
from app.domain.prediction_models import ScorecardResult


def _num(values: Mapping[str, Any], name: str) -> float | None:
    raw = values.get(name)
    if raw is None:
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):  # noqa: PLR0124
        return None
    return number


def _missing(missingness: Mapping[str, Any], name: str) -> bool:
    flag = missingness.get(name)
    if flag is None:
        return False
    try:
        return int(flag) == 1
    except (TypeError, ValueError):
        return bool(flag)


def _band(score: float) -> RiskBand:
    if score <= BAND_LOW_MAX:
        return RiskBand.LOW
    if score <= BAND_MODERATE_MAX:
        return RiskBand.MODERATE
    if score <= BAND_HIGH_MAX:
        return RiskBand.HIGH
    return RiskBand.CRITICAL


def _factor(rule_id: str, label: str, contribution: float, value: float | None) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "label": label,
        "contribution": contribution,
        "feature_value": value,
        "rule_version": SCORECARD_VERSION,
    }


class DeliveryScorecardV1:
    """Transparent rule baseline. Always returns uncalibrated_score — never a probability."""

    version = SCORECARD_VERSION

    def score(
        self,
        feature_values: Mapping[str, float | None],
        missingness: Mapping[str, int] | None = None,
    ) -> ScorecardResult:
        missingness = missingness or {}
        score = 50.0
        positive: list[dict[str, Any]] = []
        negative: list[dict[str, Any]] = []
        warnings: list[str] = []

        def apply(
            rule_id: str,
            label: str,
            delta: float,
            value: float | None,
            *,
            increases_risk: bool,
        ) -> None:
            nonlocal score
            if delta == 0.0:
                return
            score += delta
            entry = _factor(rule_id, label, delta, value)
            if increases_risk:
                negative.append(entry)
            else:
                positive.append(entry)

        readiness = _num(feature_values, "readiness_score_at_cutoff")
        if readiness is None or _missing(missingness, "readiness_score_at_cutoff"):
            warnings.append("missing:readiness_score_at_cutoff")
        elif readiness < 40.0:
            apply("readiness_low", "Low readiness score", 15.0, readiness, increases_risk=True)
        elif readiness < 60.0:
            apply(
                "readiness_moderate",
                "Moderate readiness score",
                8.0,
                readiness,
                increases_risk=True,
            )
        elif readiness >= 80.0:
            apply("readiness_high", "High readiness score", -12.0, readiness, increases_risk=False)

        confidence = _num(feature_values, "assessment_confidence_at_cutoff")
        if confidence is None or _missing(missingness, "assessment_confidence_at_cutoff"):
            warnings.append("missing:assessment_confidence_at_cutoff")
        elif confidence < 40.0:
            apply(
                "confidence_low",
                "Low assessment confidence",
                5.0,
                confidence,
                increases_risk=True,
            )

        coverage = _num(feature_values, "capability_coverage")
        if coverage is not None and not _missing(missingness, "capability_coverage"):
            if coverage >= 0.9:
                apply(
                    "capability_coverage_high",
                    "High capability coverage",
                    -8.0,
                    coverage,
                    increases_risk=False,
                )
            elif coverage < 0.5:
                apply(
                    "capability_coverage_low",
                    "Low capability coverage",
                    10.0,
                    coverage,
                    increases_risk=True,
                )

        gaps = _num(feature_values, "critical_capability_gap_count")
        if gaps is not None and gaps >= 1.0:
            delta = 10.0 * min(gaps, 3.0)
            apply(
                "critical_capability_gaps",
                "Critical capability gaps",
                delta,
                gaps,
                increases_risk=True,
            )

        risks = _num(feature_values, "unresolved_critical_risk_count")
        if risks is not None and risks >= 1.0:
            apply(
                "unresolved_critical_risks",
                "Unresolved critical risks",
                8.0 * min(risks, 3.0),
                risks,
                increases_risk=True,
            )

        cycle = _num(feature_values, "active_dependency_cycle_indicator")
        if cycle is not None and cycle >= 1.0:
            apply(
                "dependency_cycle",
                "Active dependency cycle",
                12.0,
                cycle,
                increases_risk=True,
            )

        spd = _num(feature_values, "single_person_dependency_count")
        if spd is not None and spd >= 1.0:
            apply(
                "single_person_dependency",
                "Single-person dependencies",
                10.0 * min(spd, 3.0),
                spd,
                increases_risk=True,
            )

        cross = _num(feature_values, "cross_team_dependency_count")
        if cross is not None and cross > 5.0:
            apply(
                "cross_team_dependencies",
                "Many cross-team dependencies",
                6.0,
                cross,
                increases_risk=True,
            )

        crit_findings = _num(feature_values, "finding_severity_critical_count")
        if crit_findings is not None and crit_findings > 0.0:
            apply(
                "critical_graph_findings",
                "Critical graph findings",
                12.0 * min(crit_findings, 3.0),
                crit_findings,
                increases_risk=True,
            )

        redundancy = _num(feature_values, "ownership_redundancy")
        if redundancy is not None and redundancy >= 2.0:
            apply(
                "ownership_redundancy",
                "Ownership redundancy",
                -8.0,
                redundancy,
                increases_risk=False,
            )

        unavailable = _num(feature_values, "unavailable_owner_ratio")
        if unavailable is not None and unavailable > 0.3:
            apply(
                "unavailable_owners",
                "High unavailable-owner ratio",
                10.0,
                unavailable,
                increases_risk=True,
            )

        team_avail = _num(feature_values, "team_availability_ratio")
        if team_avail is not None and team_avail >= 0.9:
            apply(
                "team_availability_high",
                "High team availability",
                -6.0,
                team_avail,
                increases_risk=False,
            )

        overdue = _num(feature_values, "overdue_work_item_count")
        if overdue is not None and overdue > 5.0:
            apply(
                "overdue_work_items",
                "Overdue work items",
                8.0,
                overdue,
                increases_risk=True,
            )

        blocked = _num(feature_values, "blocked_work_item_count")
        if blocked is not None and blocked > 3.0:
            apply(
                "blocked_work_items",
                "Blocked work items",
                8.0,
                blocked,
                increases_risk=True,
            )

        sprint = _num(feature_values, "sprint_completion_ratio")
        if sprint is not None and not _missing(missingness, "sprint_completion_ratio"):
            if sprint >= 0.8:
                apply(
                    "sprint_completion_high",
                    "High sprint completion",
                    -8.0,
                    sprint,
                    increases_risk=False,
                )
            elif sprint < 0.5:
                apply(
                    "sprint_completion_low",
                    "Low sprint completion",
                    8.0,
                    sprint,
                    increases_risk=True,
                )

        failed_deps = _num(feature_values, "failed_deployment_count_30d")
        if failed_deps is not None and failed_deps > 0.0:
            apply(
                "failed_deployments",
                "Failed deployments (30d)",
                6.0 * min(failed_deps, 3.0),
                failed_deps,
                increases_risk=True,
            )

        dep_count = _num(feature_values, "deployment_count_30d")
        if (
            dep_count is not None
            and dep_count >= 3.0
            and (failed_deps is None or failed_deps == 0.0)
        ):
            apply(
                "healthy_deployments",
                "Healthy deployment cadence",
                -5.0,
                dep_count,
                increases_risk=False,
            )

        unresolved_inc = _num(feature_values, "unresolved_incident_count")
        if unresolved_inc is not None and unresolved_inc > 0.0:
            apply(
                "unresolved_incidents",
                "Unresolved incidents",
                8.0 * min(unresolved_inc, 3.0),
                unresolved_inc,
                increases_risk=True,
            )

        if _num(feature_values, "missing_owner_indicator") == 1.0:
            apply("missing_owner", "Missing owner", 6.0, 1.0, increases_risk=True)
            warnings.append("missing_owner")

        if _num(feature_values, "incomplete_history_indicator") == 1.0:
            apply(
                "incomplete_history",
                "Incomplete history",
                5.0,
                1.0,
                increases_risk=True,
            )
            warnings.append("incomplete_history")

        stale = _num(feature_values, "stale_source_count")
        if stale is not None and stale > 2.0:
            apply("stale_sources", "Stale data sources", 5.0, stale, increases_risk=True)
            warnings.append("stale_sources")

        source_cov = _num(feature_values, "source_coverage_ratio")
        if source_cov is not None and source_cov >= 0.8:
            apply(
                "source_coverage_high",
                "High source coverage",
                -4.0,
                source_cov,
                increases_risk=False,
            )
        elif source_cov is None or _missing(missingness, "source_coverage_ratio"):
            warnings.append("missing:source_coverage_ratio")

        score = max(0.0, min(100.0, score))
        positive.sort(key=lambda f: abs(float(f["contribution"])), reverse=True)
        negative.sort(key=lambda f: abs(float(f["contribution"])), reverse=True)

        return ScorecardResult(
            estimate_kind=EstimateKind.UNCALIBRATED_SCORE,
            delivery_risk_score=round(score, 4),
            risk_band=_band(score),
            positive_factors=positive[:8],
            negative_factors=negative[:8],
            missing_data_warnings=warnings[:32],
            scorecard_version=SCORECARD_VERSION,
        )
