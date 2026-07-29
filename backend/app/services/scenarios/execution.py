"""Scenario execution engine — deterministic overlay pipeline."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.scenario_constants import (
    DEFAULT_HORIZON_DAYS,
    RESULT_HASH_VERSION,
    SCENARIO_SCHEMA_VERSION,
)
from app.domain.scenario_enums import (
    ScenarioKind,
    ScenarioRunMode,
    ScenarioRunState,
    ScenarioTargetType,
)
from app.domain.scenario_models import (
    ScenarioExecutionBundle,
    ScenarioResult,
    ScenarioRun,
)
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import (
    EnterpriseConflictError,
)
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.scenarios.baseline import BaselineCaptureService
from app.services.scenarios.feature_overlay import ScenarioFeatureOverlayService
from app.services.scenarios.fingerprints import compute_source_fingerprint
from app.services.scenarios.graph_overlay import ScenarioGraphOverlayEngine
from app.services.scenarios.impacts import build_impacts
from app.services.scenarios.prediction_adapter import ScenarioPredictionAdapter
from app.services.scenarios.validation import normalize_assumptions

logger = logging.getLogger("signalforge.scenarios")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ScenarioExecutionService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._baseline = BaselineCaptureService(uow)
        self._graph = ScenarioGraphOverlayEngine(uow)
        self._features = ScenarioFeatureOverlayService()
        self._prediction = ScenarioPredictionAdapter(uow)

    def execute(
        self,
        ctx: TenantContext,
        *,
        scenario_version_id: str,
        as_of_at: datetime | None = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        run_mode: ScenarioRunMode = ScenarioRunMode.MANUAL,
        force_model_id: str | None = None,
    ) -> ScenarioExecutionBundle:
        version = self._uow.scenario_versions.require(ctx, scenario_version_id)
        definition = self._uow.scenario_definitions.require(ctx, version.scenario_definition_id)
        as_of = _aware(as_of_at or _utcnow())
        assumptions = normalize_assumptions(definition.scenario_kind, version.assumptions)

        logger.info(
            "scenario.execution.started tenant_id=%s version_id=%s target=%s/%s",
            ctx.tenant_id,
            version.scenario_version_id,
            definition.target_type.value
            if hasattr(definition.target_type, "value")
            else definition.target_type,
            definition.target_id,
        )

        source_parts = compute_source_fingerprint(
            self._uow,
            ctx,
            target_type=definition.target_type,
            target_id=definition.target_id,
            as_of_at=as_of,
            horizon_days=horizon_days,
            scenario_version_hash=version.specification_hash,
        )
        baseline = self._baseline.capture(
            ctx,
            target_type=definition.target_type,
            target_id=definition.target_id,
            as_of_at=as_of,
            horizon_days=horizon_days,
            scenario_version_hash=version.specification_hash,
            source_parts=source_parts,
        )
        logger.info(
            "scenario.baseline.captured tenant_id=%s fingerprint=%s",
            ctx.tenant_id,
            baseline.baseline_fingerprint[:16],
        )

        scenario_fingerprint = snapshot_hash(
            {
                "specification_hash": version.specification_hash,
                "assumptions": assumptions,
                "schema": SCENARIO_SCHEMA_VERSION,
            }
        )
        run_input_hash = snapshot_hash(
            {
                "scenario_version_hash": version.specification_hash,
                "as_of_at": as_of.isoformat(),
                "horizon_days": horizon_days,
                "source_fingerprint": baseline.source_fingerprint,
                "graph_projection_version": baseline.graph_projection_version,
                "prediction_baseline_version": baseline.prediction_baseline_version,
            }
        )

        existing = self._uow.scenario_runs.get_by_input_hash(ctx, run_input_hash)
        if existing is not None and existing.state in {
            ScenarioRunState.SUCCEEDED,
            ScenarioRunState.PARTIAL,
        }:
            result = self._uow.scenario_results.get_by_run(ctx, existing.scenario_run_id)
            impacts = self._uow.scenario_impacts.list_for_run(
                ctx, existing.scenario_run_id, limit=250, offset=0
            ).items
            overlay = self._uow.scenario_feature_overlays.get_by_run(ctx, existing.scenario_run_id)
            logger.info(
                "scenario.execution.idempotent_reuse tenant_id=%s run_id=%s",
                ctx.tenant_id,
                existing.scenario_run_id,
            )
            return ScenarioExecutionBundle(
                run=existing,
                result=result,
                impacts=list(impacts),
                feature_overlay=overlay,
                reused_existing=True,
            )

        started = _utcnow()
        run = ScenarioRun(
            tenant_id=ctx.tenant_id,
            scenario_run_id=build_entity_id(
                "srun",
                ctx.tenant_id,
                version.scenario_version_id,
                run_input_hash,
            ),
            scenario_version_id=version.scenario_version_id,
            scenario_definition_id=definition.scenario_definition_id,
            target_type=ScenarioTargetType(definition.target_type),
            target_id=definition.target_id,
            as_of_at=as_of,
            horizon_days=horizon_days,
            run_mode=run_mode,
            source_fingerprint=baseline.source_fingerprint,
            baseline_fingerprint=baseline.baseline_fingerprint,
            scenario_fingerprint=scenario_fingerprint,
            run_input_hash=run_input_hash,
            graph_projection_version=baseline.graph_projection_version,
            prediction_model_id=baseline.prediction_model_id,
            prediction_baseline_version=baseline.prediction_baseline_version,
            state=ScenarioRunState.RUNNING,
            started_at=started,
        )
        try:
            run = self._uow.scenario_runs.create(ctx, run)
        except EnterpriseConflictError:
            # Concurrent creator won — reuse.
            existing = self._uow.scenario_runs.get_by_input_hash(ctx, run_input_hash)
            if existing is None:
                raise
            result = self._uow.scenario_results.get_by_run(ctx, existing.scenario_run_id)
            impacts = self._uow.scenario_impacts.list_for_run(
                ctx, existing.scenario_run_id, limit=250, offset=0
            ).items
            overlay = self._uow.scenario_feature_overlays.get_by_run(ctx, existing.scenario_run_id)
            return ScenarioExecutionBundle(
                run=existing,
                result=result,
                impacts=list(impacts),
                feature_overlay=overlay,
                reused_existing=True,
            )

        try:
            graph_overlay = self._graph.apply(
                ctx,
                target_type=definition.target_type.value
                if hasattr(definition.target_type, "value")
                else str(definition.target_type),
                target_id=definition.target_id,
                as_of_at=as_of,
                assumptions=assumptions,
                baseline_finding_summaries=baseline.finding_summaries,
            )
            logger.info(
                "scenario.graph_overlay.applied tenant_id=%s nodes=%s edges=%s added=%s",
                ctx.tenant_id,
                graph_overlay.nodes_examined,
                graph_overlay.edges_examined,
                len(graph_overlay.findings_added),
            )

            feature_overlay = self._features.build(
                ctx,
                scenario_run_id=run.scenario_run_id,
                assumptions=assumptions,
                baseline=baseline,
                graph_overlay=graph_overlay,
            )
            self._uow.scenario_feature_overlays.create(ctx, feature_overlay)
            logger.info(
                "scenario.feature_overlay.created tenant_id=%s overlay_id=%s training_eligible=%s",
                ctx.tenant_id,
                feature_overlay.scenario_feature_overlay_id,
                False,
            )

            pred_pair = self._prediction.evaluate_pair(
                ctx,
                baseline=baseline,
                simulated_feature_values=feature_overlay.simulated_feature_values,
                force_model_id=force_model_id,
            )
            if pred_pair.baseline.estimate_kind.value == "uncalibrated_score":
                logger.info(
                    "scenario.prediction.fallback_used tenant_id=%s run_id=%s",
                    ctx.tenant_id,
                    run.scenario_run_id,
                )
            else:
                logger.info(
                    "scenario.prediction.calibrated_used tenant_id=%s run_id=%s model_id=%s",
                    ctx.tenant_id,
                    run.scenario_run_id,
                    pred_pair.baseline.model_id,
                )

            impacts = build_impacts(
                ctx,
                scenario_run_id=run.scenario_run_id,
                graph_overlay=graph_overlay,
                prediction_pair=pred_pair,
            )

            result = self._build_result(
                ctx,
                run=run,
                version=version,
                assumptions=assumptions,
                baseline=baseline,
                graph_overlay=graph_overlay,
                pred_pair=pred_pair,
                kind=ScenarioKind(definition.scenario_kind),
            )
            self._uow.scenario_results.create(ctx, result)
            if impacts:
                self._uow.scenario_impacts.create_many(ctx, impacts)

            state = (
                ScenarioRunState.PARTIAL if graph_overlay.truncated else ScenarioRunState.SUCCEEDED
            )
            run = self._uow.scenario_runs.update_state(
                ctx,
                run.scenario_run_id,
                state,
                completed_at=_utcnow(),
                nodes_examined=graph_overlay.nodes_examined,
                edges_examined=graph_overlay.edges_examined,
                impacts_created=len(impacts),
                result_hash=result.result_hash,
            )
            logger.info(
                "scenario.execution.completed tenant_id=%s run_id=%s state=%s result_hash=%s",
                ctx.tenant_id,
                run.scenario_run_id,
                state.value,
                result.result_hash[:16],
            )
            return ScenarioExecutionBundle(
                run=run,
                result=result,
                impacts=impacts,
                feature_overlay=feature_overlay,
                reused_existing=False,
            )
        except Exception as exc:
            sanitized = str(exc)[:512]
            try:
                self._uow.scenario_runs.update_state(
                    ctx,
                    run.scenario_run_id,
                    ScenarioRunState.FAILED,
                    completed_at=_utcnow(),
                    sanitized_error_summary=sanitized,
                )
            except Exception:
                # Session may have been rolled back by an integrity guard.
                self._uow.rollback()
            logger.info(
                "scenario.execution.failed tenant_id=%s run_id=%s error=%s",
                ctx.tenant_id,
                run.scenario_run_id,
                sanitized,
            )
            raise

    def _build_result(self, ctx, **kwargs) -> ScenarioResult:
        run: ScenarioRun = kwargs["run"]
        assumptions: dict[str, Any] = kwargs["assumptions"]
        baseline = kwargs["baseline"]
        graph_overlay = kwargs["graph_overlay"]
        pred_pair = kwargs["pred_pair"]
        kind: ScenarioKind = kwargs["kind"]

        baseline_summary = {
            "finding_count": len(graph_overlay.baseline_findings),
            "graph_node_count": baseline.graph_node_count,
            "graph_edge_count": baseline.graph_edge_count,
            "estimate_kind": pred_pair.baseline.estimate_kind.value,
            "risk_score": pred_pair.baseline.risk_score,
            "probability": pred_pair.baseline.probability,
        }
        simulated_summary = {
            "finding_count": len(graph_overlay.simulated_findings),
            "impacted_nodes": len(graph_overlay.impacted_node_ids),
            "blast_radius_node_count": graph_overlay.blast_radius_node_count,
            "estimate_kind": pred_pair.simulated.estimate_kind.value,
            "risk_score": pred_pair.simulated.risk_score,
            "probability": pred_pair.simulated.probability,
        }
        delta_summary = {
            "findings_added": len(graph_overlay.findings_added),
            "findings_removed": len(graph_overlay.findings_removed),
            "findings_worsened": len(graph_overlay.findings_worsened),
            "findings_improved": len(graph_overlay.findings_improved),
            "ownership_concentration_delta": graph_overlay.ownership_concentration_delta,
            "capability_concentration_delta": graph_overlay.capability_concentration_delta,
            "dependency_delay_days": graph_overlay.dependency_delay_days,
            "probability_delta": pred_pair.probability_delta,
            "risk_score_delta": pred_pair.risk_score_delta,
            "estimate_comparability": pred_pair.estimate_comparability.value,
        }
        warnings = list(baseline.data_quality_warnings)
        applicability = []
        if pred_pair.baseline.estimate_kind.value == "uncalibrated_score":
            applicability.append("uncalibrated_score_not_probability")
        if graph_overlay.truncated:
            warnings.append("graph_overlay_truncated")

        result_hash = snapshot_hash(
            {
                "version": RESULT_HASH_VERSION,
                "run_input_hash": run.run_input_hash,
                "baseline_summary": baseline_summary,
                "simulated_summary": simulated_summary,
                "delta_summary": delta_summary,
                "estimate_kind": pred_pair.simulated.estimate_kind.value,
                "warnings": sorted(set(warnings)),
                "impacts_fingerprint": snapshot_hash(
                    {
                        "added": [f.finding_key for f in graph_overlay.findings_added],
                        "projects": graph_overlay.impacted_project_ids,
                        "initiatives": graph_overlay.impacted_initiative_ids,
                    }
                ),
            }
        )
        return ScenarioResult(
            tenant_id=ctx.tenant_id,
            scenario_result_id=build_entity_id(
                "sres", ctx.tenant_id, run.scenario_run_id, result_hash
            ),
            scenario_run_id=run.scenario_run_id,
            target_type=run.target_type,
            target_id=run.target_id,
            as_of_at=run.as_of_at,
            horizon_days=run.horizon_days,
            scenario_kind=kind,
            baseline_summary=baseline_summary,
            simulated_summary=simulated_summary,
            delta_summary=delta_summary,
            baseline_estimate_kind=pred_pair.baseline.estimate_kind,
            simulated_estimate_kind=pred_pair.simulated.estimate_kind,
            estimate_comparability=pred_pair.estimate_comparability,
            baseline_probability=pred_pair.baseline.probability,
            simulated_probability=pred_pair.simulated.probability,
            probability_delta=pred_pair.probability_delta,
            baseline_risk_score=pred_pair.baseline.risk_score,
            simulated_risk_score=pred_pair.simulated.risk_score,
            risk_score_delta=pred_pair.risk_score_delta,
            baseline_risk_band=pred_pair.baseline.risk_band,
            simulated_risk_band=pred_pair.simulated.risk_band,
            affected_project_count=len(graph_overlay.impacted_project_ids),
            affected_initiative_count=len(graph_overlay.impacted_initiative_ids),
            affected_critical_initiative_count=len(graph_overlay.critical_initiative_ids),
            findings_added_count=len(graph_overlay.findings_added),
            findings_removed_count=len(graph_overlay.findings_removed),
            findings_worsened_count=len(graph_overlay.findings_worsened),
            findings_improved_count=len(graph_overlay.findings_improved),
            data_quality_warnings=sorted(set(warnings))[:32],
            applicability_warnings=sorted(set(applicability))[:32],
            assumption_summary={
                "kind": assumptions.get("kind"),
                "change_count": len(assumptions.get("changes") or []),
                "schema_version": assumptions.get("schema_version"),
            },
            result_hash=result_hash,
        )
