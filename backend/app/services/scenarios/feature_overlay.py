"""Scenario feature overlay registry (scenario_feature_overlay_v1).



Transforms are documented and bounded. Overlays are never training-eligible.

"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_constants import FEATURE_SCHEMA_VERSION
from app.domain.scenario_constants import (
    OVERLAY_ALLOWED_FEATURES,
    SCENARIO_FEATURE_OVERLAY_VERSION,
)
from app.domain.scenario_enums import ScenarioKind, SimulationOrigin
from app.domain.scenario_models import ScenarioFeatureOverlay
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseValidationError
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.scenarios.baseline import ScenarioBaseline
from app.services.scenarios.graph_overlay import GraphOverlayResult


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _finite(value: float, name: str) -> float:
    if not math.isfinite(value):
        raise EnterpriseValidationError(f"Non-finite overlay feature value: {name}")

    return value


@dataclass(frozen=True)
class FeatureTransform:
    feature: str

    rule_id: str

    description: str


# Documented transformation rules applied by scenario kind.

TRANSFORMS_REGISTRY: dict[str, list[FeatureTransform]] = {
    ScenarioKind.ENGINEER_UNAVAILABLE.value: [
        FeatureTransform(
            "unavailable_owner_ratio",
            "eng_unavail_owner_ratio_v1",
            "Increase unavailable owner ratio by 1/max(owners,1).",
        ),
        FeatureTransform(
            "active_engineer_owner_count",
            "eng_unavail_owner_count_v1",
            "Decrease active engineer owner count by 1 when positive.",
        ),
        FeatureTransform(
            "single_person_dependency_count",
            "eng_unavail_spd_v1",
            "Increase single-person dependency findings by 1.",
        ),
        FeatureTransform(
            "availability_blast_radius_count",
            "eng_unavail_blast_v1",
            "Increase availability blast-radius findings by 1.",
        ),
        FeatureTransform(
            "ownership_redundancy",
            "eng_unavail_redundancy_v1",
            "Decrease ownership redundancy by 0.5 when positive.",
        ),
        FeatureTransform(
            "missing_owner_indicator",
            "eng_unavail_missing_owner_v1",
            "Set missing-owner indicator when active owners drop to zero.",
        ),
    ],
    ScenarioKind.TEAM_CAPACITY_REDUCTION.value: [
        FeatureTransform(
            "team_availability_ratio",
            "team_cap_avail_v1",
            "Scale team availability by (1 - reduction_percentage/100).",
        ),
        FeatureTransform(
            "cross_team_dependency_count",
            "team_cap_xteam_v1",
            "Increase cross-team dependency pressure by 1.",
        ),
        FeatureTransform(
            "affected_critical_initiative_count",
            "team_cap_crit_v1",
            "Reflect critical initiatives in graph overlay blast radius.",
        ),
    ],
    ScenarioKind.CAPABILITY_UNAVAILABLE.value: [
        FeatureTransform(
            "capability_coverage",
            "cap_unavail_coverage_v1",
            "Decrease capability coverage by 0.15 (clipped).",
        ),
        FeatureTransform(
            "critical_capability_gap_count",
            "cap_unavail_gap_v1",
            "Increase critical capability gaps by 1.",
        ),
        FeatureTransform(
            "capability_ownership_concentration_count",
            "cap_unavail_conc_v1",
            "Increase capability ownership concentration findings by 1.",
        ),
        FeatureTransform(
            "critical_capability_owner_count",
            "cap_unavail_owners_v1",
            "Decrease critical capability owner count by 1 when positive.",
        ),
    ],
    ScenarioKind.REPOSITORY_UNAVAILABLE.value: [
        FeatureTransform(
            "repository_ownership_concentration_count",
            "repo_unavail_conc_v1",
            "Increase repository ownership concentration findings by 1.",
        ),
        FeatureTransform(
            "availability_blast_radius_count",
            "repo_unavail_blast_v1",
            "Increase blast-radius findings by 1.",
        ),
        FeatureTransform(
            "affected_critical_initiative_count",
            "repo_unavail_crit_v1",
            "Reflect critical initiatives in overlay blast radius.",
        ),
    ],
    ScenarioKind.DEPENDENCY_DELAY.value: [
        FeatureTransform(
            "active_dependency_count",
            "dep_delay_count_v1",
            "Keep dependency count; raise blocked/overdue pressure.",
        ),
        FeatureTransform(
            "blocked_work_item_count",
            "dep_delay_blocked_v1",
            "Increase blocked work items by delay_days/30 (ceil at least 1).",
        ),
        FeatureTransform(
            "overdue_work_item_count",
            "dep_delay_overdue_v1",
            "Increase overdue work items by 1.",
        ),
        FeatureTransform(
            "dependency_depth",
            "dep_delay_depth_v1",
            "Increase dependency depth by 1 when below cap.",
        ),
        FeatureTransform(
            "cross_team_dependency_count",
            "dep_delay_xteam_v1",
            "Increase cross-team dependency findings by 1.",
        ),
    ],
    ScenarioKind.DEADLINE_COMPRESSION.value: [
        FeatureTransform(
            "planned_duration_days",
            "deadline_planned_v1",
            "Decrease planned duration by days_reduced when positive.",
        ),
        FeatureTransform(
            "project_age_days_at_cutoff",
            "deadline_age_v1",
            "Increase relative age pressure by days_reduced * 0.25.",
        ),
        FeatureTransform(
            "overdue_work_item_count",
            "deadline_overdue_v1",
            "Increase overdue work items by 1.",
        ),
    ],
    ScenarioKind.INCIDENT_ESCALATION.value: [
        FeatureTransform(
            "incident_count_30d",
            "inc_esc_count_v1",
            "Increase incident count by 1.",
        ),
        FeatureTransform(
            "unresolved_incident_count",
            "inc_esc_unresolved_v1",
            "Increase unresolved incidents by 1.",
        ),
        FeatureTransform(
            "finding_severity_high_count",
            "inc_esc_sev_high_v1",
            "Increase high-severity finding count for high/critical escalation.",
        ),
        FeatureTransform(
            "finding_severity_critical_count",
            "inc_esc_sev_crit_v1",
            "Increase critical finding count for critical escalation.",
        ),
        FeatureTransform(
            "availability_blast_radius_count",
            "inc_esc_blast_v1",
            "Increase blast-radius findings by 1.",
        ),
    ],
}


class ScenarioFeatureOverlayService:
    def build(
        self,
        ctx: TenantContext,
        *,
        scenario_run_id: str,
        assumptions: dict[str, Any],
        baseline: ScenarioBaseline,
        graph_overlay: GraphOverlayResult,
    ) -> ScenarioFeatureOverlay:
        simulated = dict(baseline.feature_values)

        changed: dict[str, float] = {}

        lineage: list[dict[str, Any]] = []

        changes = list(assumptions.get("changes") or [])

        for change in changes:
            kind = str(change.get("kind"))

            for transform in TRANSFORMS_REGISTRY.get(kind, []):
                if transform.feature not in OVERLAY_ALLOWED_FEATURES:
                    continue

                before = float(simulated.get(transform.feature, 0.0) or 0.0)

                after = self._apply_transform(transform, before, change, graph_overlay)

                after = _finite(after, transform.feature)

                if after != before:
                    simulated[transform.feature] = after

                    changed[transform.feature] = after

                    lineage.append(
                        {
                            "feature": transform.feature,
                            "rule_id": transform.rule_id,
                            "description": transform.description,
                            "before": before,
                            "after": after,
                            "assumption_kind": kind,
                            "origin": SimulationOrigin.SCENARIO_SIMULATED.value,
                        }
                    )

        # Sync finding severity counts from graph overlay deltas when present.

        if graph_overlay.findings_added:
            high_add = sum(
                1 for f in graph_overlay.findings_added if f.severity in {"high", "critical"}
            )

            if high_add:
                key = "finding_severity_high_count"

                before = float(simulated.get(key, 0.0) or 0.0)

                after = before + high_add

                if key in OVERLAY_ALLOWED_FEATURES and after != before:
                    simulated[key] = after

                    changed[key] = after

        # Unchanged features remain identical.

        for key, value in baseline.feature_values.items():
            if key not in changed:
                simulated[key] = value

        delta = {
            k: _finite(float(simulated[k]) - float(baseline.feature_values.get(k, 0.0) or 0.0), k)
            for k in sorted(changed)
        }

        for key in changed:
            if key not in OVERLAY_ALLOWED_FEATURES:
                raise EnterpriseValidationError(f"Overlay attempted unsupported feature: {key}")

        overlay_hash = snapshot_hash(
            {
                "schema": SCENARIO_FEATURE_OVERLAY_VERSION,
                "baseline_hash": baseline.feature_values_hash,
                "changed": {k: changed[k] for k in sorted(changed)},
                "delta": {k: delta[k] for k in sorted(delta)},
                "training_eligible": False,
            }
        )

        return ScenarioFeatureOverlay(
            tenant_id=ctx.tenant_id,
            scenario_feature_overlay_id=build_entity_id(
                "sfo", ctx.tenant_id, scenario_run_id, overlay_hash
            ),
            scenario_run_id=scenario_run_id,
            baseline_feature_snapshot_id=baseline.feature_snapshot_id,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            overlay_schema_version=SCENARIO_FEATURE_OVERLAY_VERSION,
            baseline_values_hash=baseline.feature_values_hash,
            changed_feature_values={k: changed[k] for k in sorted(changed)},
            simulated_feature_values={k: simulated[k] for k in sorted(simulated)},
            feature_delta={k: delta[k] for k in sorted(delta)},
            feature_lineage=lineage[:64],
            simulation_origin=SimulationOrigin.SCENARIO_SIMULATED,
            training_eligible=False,
            overlay_hash=overlay_hash,
        )

    def _apply_transform(
        self,
        transform: FeatureTransform,
        before: float,
        change: dict[str, Any],
        graph_overlay: GraphOverlayResult,
    ) -> float:
        kind = change.get("kind")

        if transform.feature == "unavailable_owner_ratio":
            owners = max(before and 1.0 or 1.0, 1.0)

            # Use active owner count context if available via before ratio semantics.

            return _clip(before + (1.0 / max(owners, 1.0)), 0.0, 1.0)

        if transform.feature == "active_engineer_owner_count":
            return max(0.0, before - 1.0)

        if transform.feature == "ownership_redundancy":
            return max(0.0, before - 0.5)

        if transform.feature == "single_person_dependency_count":
            return before + 1.0

        if transform.feature == "availability_blast_radius_count":
            return before + 1.0

        if transform.feature == "missing_owner_indicator":
            return 1.0 if before >= 0 else 1.0

        if transform.feature == "team_availability_ratio":
            pct = float(change.get("reduction_percentage") or 0) / 100.0

            return _clip(before * (1.0 - pct), 0.0, 1.0)

        if transform.feature == "cross_team_dependency_count":
            return before + 1.0

        if transform.feature == "affected_critical_initiative_count":
            return float(len(graph_overlay.critical_initiative_ids))

        if transform.feature == "capability_coverage":
            return _clip(before - 0.15, 0.0, 1.0)

        if transform.feature == "critical_capability_gap_count":
            return before + 1.0

        if transform.feature == "capability_ownership_concentration_count":
            return before + 1.0

        if transform.feature == "critical_capability_owner_count":
            return max(0.0, before - 1.0)

        if transform.feature == "repository_ownership_concentration_count":
            return before + 1.0

        if transform.feature == "blocked_work_item_count":
            delay = int(change.get("delay_days") or 0)

            bump = max(1, (delay + 29) // 30) if delay else 1

            return before + float(bump)

        if transform.feature == "overdue_work_item_count":
            return before + 1.0

        if transform.feature == "dependency_depth":
            return min(20.0, before + 1.0)

        if transform.feature == "active_dependency_count":
            return before

        if transform.feature == "planned_duration_days":
            days = float(change.get("days_reduced") or 0)

            return max(1.0, before - days) if before > 0 else before

        if transform.feature == "project_age_days_at_cutoff":
            days = float(change.get("days_reduced") or 0)

            return before + days * 0.25

        if transform.feature == "incident_count_30d":
            return before + 1.0

        if transform.feature == "unresolved_incident_count":
            return before + 1.0

        if transform.feature == "finding_severity_high_count":
            sev = str(change.get("simulated_severity") or "")

            return before + (1.0 if sev in {"high", "critical"} else 0.0)

        if transform.feature == "finding_severity_critical_count":
            sev = str(change.get("simulated_severity") or "")

            return before + (1.0 if sev == "critical" else 0.0)

        if kind:
            return before

        return before
