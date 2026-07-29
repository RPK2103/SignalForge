"""Scenario impact builders — responsible-use wording only."""

from __future__ import annotations

from app.domain.enterprise_identifiers import build_entity_id
from app.domain.scenario_constants import FORBIDDEN_OUTPUT_PHRASES, MAX_IMPACTS_PER_RESULT
from app.domain.scenario_enums import (
    ImpactDirection,
    ImpactSeverity,
    ScenarioImpactConfidence,
    ScenarioImpactType,
)
from app.domain.scenario_models import ScenarioImpact
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseValidationError
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.scenarios.graph_overlay import GraphOverlayResult
from app.services.scenarios.prediction_adapter import ScenarioPredictionPair


def _safe_explanation(text: str) -> str:
    lower = text.lower()
    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        if phrase in lower:
            raise EnterpriseValidationError("Impact explanation violates responsible-use wording")
    if not text.startswith("This scenario"):
        text = f"This scenario {text[0].lower() + text[1:]}" if text else text
    return text[:512]


def build_impacts(
    ctx: TenantContext,
    *,
    scenario_run_id: str,
    graph_overlay: GraphOverlayResult,
    prediction_pair: ScenarioPredictionPair,
) -> list[ScenarioImpact]:
    impacts: list[ScenarioImpact] = []

    def _add(
        *,
        impact_type: ScenarioImpactType,
        explanation: str,
        direction: ImpactDirection,
        severity: ImpactSeverity = ImpactSeverity.MEDIUM,
        primary_node_id: str | None = None,
        affected_node_ids: list[str] | None = None,
        supporting_edge_ids: list[str] | None = None,
        assumption_ids: list[str] | None = None,
        magnitude: float | None = None,
        unit: str | None = None,
        confidence: ScenarioImpactConfidence = ScenarioImpactConfidence.HIGH,
    ) -> None:
        if len(impacts) >= MAX_IMPACTS_PER_RESULT:
            return
        safe = _safe_explanation(explanation)
        payload = {
            "impact_type": impact_type.value,
            "scenario_run_id": scenario_run_id,
            "primary_node_id": primary_node_id,
            "affected_node_ids": sorted(affected_node_ids or [])[:100],
            "explanation": safe,
            "magnitude": magnitude,
        }
        impact_hash = snapshot_hash(payload)
        impacts.append(
            ScenarioImpact(
                tenant_id=ctx.tenant_id,
                scenario_impact_id=build_entity_id(
                    "simp", ctx.tenant_id, scenario_run_id, impact_hash
                ),
                scenario_run_id=scenario_run_id,
                impact_type=impact_type,
                primary_node_id=primary_node_id,
                affected_node_ids=sorted(affected_node_ids or [])[:100],
                supporting_edge_ids=sorted(supporting_edge_ids or [])[:50],
                supporting_evidence_signal_ids=[],
                assumption_ids=list(assumption_ids or graph_overlay.assumption_ids)[:20],
                direction=direction,
                magnitude=magnitude,
                unit=unit,
                severity=severity,
                confidence=confidence,
                explanation=safe,
                impact_hash=impact_hash,
            )
        )

    for node_id in graph_overlay.impacted_node_ids[:50]:
        _add(
            impact_type=ScenarioImpactType.NODE_AFFECTED,
            explanation="This scenario affects a delivery-graph node under explicit assumptions.",
            direction=ImpactDirection.WORSENED,
            primary_node_id=node_id,
            affected_node_ids=[node_id],
            severity=ImpactSeverity.LOW,
        )

    for project_id in graph_overlay.impacted_project_ids:
        _add(
            impact_type=ScenarioImpactType.PROJECT_AFFECTED,
            explanation="This scenario affects a project in the overlay blast radius.",
            direction=ImpactDirection.WORSENED,
            affected_node_ids=[project_id],
            severity=ImpactSeverity.MEDIUM,
        )

    for initiative_id in graph_overlay.impacted_initiative_ids:
        _add(
            impact_type=ScenarioImpactType.INITIATIVE_AFFECTED,
            explanation="This scenario affects an initiative along simulated dependency paths.",
            direction=ImpactDirection.WORSENED,
            affected_node_ids=[initiative_id],
            severity=ImpactSeverity.HIGH
            if initiative_id in graph_overlay.critical_initiative_ids
            else ImpactSeverity.MEDIUM,
        )

    for finding in graph_overlay.findings_added[:40]:
        _add(
            impact_type=ScenarioImpactType.FINDING_ADDED,
            explanation=finding.explanation
            or "This scenario adds a simulated graph finding under explicit assumptions.",
            direction=ImpactDirection.WORSENED,
            primary_node_id=finding.primary_node_id,
            affected_node_ids=finding.affected_node_ids,
            supporting_edge_ids=finding.supporting_edge_ids,
            severity=ImpactSeverity(finding.severity)
            if finding.severity in {"low", "medium", "high", "critical"}
            else ImpactSeverity.MEDIUM,
        )

    for finding in graph_overlay.findings_removed[:20]:
        _add(
            impact_type=ScenarioImpactType.FINDING_REMOVED,
            explanation="This scenario removes a baseline finding under explicit assumptions.",
            direction=ImpactDirection.IMPROVED,
            primary_node_id=finding.primary_node_id,
            affected_node_ids=finding.affected_node_ids,
            severity=ImpactSeverity.LOW,
        )

    if graph_overlay.ownership_concentration_delta > 0:
        _add(
            impact_type=ScenarioImpactType.OWNERSHIP_CONCENTRATION_INCREASED,
            explanation="This scenario increases ownership concentration.",
            direction=ImpactDirection.WORSENED,
            magnitude=graph_overlay.ownership_concentration_delta,
            unit="concentration_delta",
            severity=ImpactSeverity.HIGH,
        )

    if graph_overlay.capability_concentration_delta > 0:
        _add(
            impact_type=ScenarioImpactType.CAPABILITY_CONCENTRATION_INCREASED,
            explanation="This scenario increases capability concentration.",
            direction=ImpactDirection.WORSENED,
            magnitude=graph_overlay.capability_concentration_delta,
            unit="concentration_delta",
            severity=ImpactSeverity.HIGH,
        )

    if graph_overlay.dependency_delay_days > 0:
        _add(
            impact_type=ScenarioImpactType.DEPENDENCY_DELAY_INTRODUCED,
            explanation="This scenario introduces a simulated dependency delay.",
            direction=ImpactDirection.WORSENED,
            magnitude=float(graph_overlay.dependency_delay_days),
            unit="days",
            severity=ImpactSeverity.MEDIUM,
        )

    for path in graph_overlay.path_explanations[:20]:
        _add(
            impact_type=ScenarioImpactType.PATH_AFFECTED,
            explanation="This scenario affects a bounded delivery-graph path.",
            direction=ImpactDirection.WORSENED,
            primary_node_id=(path.get("node_ids") or [None])[0],
            affected_node_ids=list(path.get("node_ids") or [])[:50],
            supporting_edge_ids=list(path.get("edge_ids") or [])[:50],
            severity=ImpactSeverity.MEDIUM,
        )

    if (
        prediction_pair.risk_score_delta is not None
        and abs(prediction_pair.risk_score_delta) > 1e-9
    ):
        _add(
            impact_type=ScenarioImpactType.PREDICTION_SCORE_CHANGED,
            explanation=(
                "This scenario changes the simulated fallback risk score "
                "under explicit assumptions."
            ),
            direction=ImpactDirection.WORSENED
            if prediction_pair.risk_score_delta > 0
            else ImpactDirection.IMPROVED,
            magnitude=float(prediction_pair.risk_score_delta),
            unit="risk_score_points",
            severity=ImpactSeverity.MEDIUM,
        )

    if (
        prediction_pair.probability_delta is not None
        and abs(prediction_pair.probability_delta) > 1e-12
    ):
        _add(
            impact_type=ScenarioImpactType.PREDICTION_PROBABILITY_CHANGED,
            explanation=(
                "This scenario changes the simulated calibrated delivery probability "
                "under explicit assumptions."
            ),
            direction=ImpactDirection.WORSENED
            if prediction_pair.probability_delta < 0
            else ImpactDirection.IMPROVED,
            magnitude=float(prediction_pair.probability_delta),
            unit="probability",
            severity=ImpactSeverity.MEDIUM,
        )

    if prediction_pair.estimate_comparability.value == "incomparable_estimate_kind":
        _add(
            impact_type=ScenarioImpactType.ESTIMATE_INCOMPARABLE,
            explanation=(
                "This scenario cannot produce a numeric estimate delta because baseline and "
                "simulated estimate kinds differ."
            ),
            direction=ImpactDirection.UNKNOWN,
            severity=ImpactSeverity.LOW,
            confidence=ScenarioImpactConfidence.MEDIUM,
        )

    return impacts[:MAX_IMPACTS_PER_RESULT]
