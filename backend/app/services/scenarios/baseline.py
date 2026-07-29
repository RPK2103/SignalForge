"""Baseline snapshot capture for scenario runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_constants import SCORECARD_VERSION, TARGET_DEFINITION
from app.domain.prediction_enums import EstimateKind, ModelUsageScope, PredictionTargetType
from app.domain.scenario_enums import ScenarioTargetType
from app.domain.tenant_context import TenantContext
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction.feature_extractor import FeatureExtractor
from app.services.scenarios.fingerprints import SourceFingerprintParts, compute_source_fingerprint


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class ScenarioBaseline:
    target_type: ScenarioTargetType
    target_id: str
    as_of_at: datetime
    horizon_days: int
    source_fingerprint: str
    source_components: dict[str, str]
    baseline_fingerprint: str
    graph_projection_version: str | None
    graph_node_count: int
    graph_edge_count: int
    finding_hashes: list[str]
    finding_summaries: list[dict[str, Any]]
    feature_snapshot_id: str | None
    feature_values: dict[str, float]
    missingness: dict[str, int]
    feature_values_hash: str
    prediction_model_id: str | None
    prediction_baseline_version: str
    estimate_kind_hint: EstimateKind
    data_quality_warnings: list[str] = field(default_factory=list)
    data_scope: str = "synthetic"


class BaselineCaptureService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._extractor = FeatureExtractor(uow)

    def capture(
        self,
        ctx: TenantContext,
        *,
        target_type: ScenarioTargetType | str,
        target_id: str,
        as_of_at: datetime,
        horizon_days: int,
        scenario_version_hash: str,
        source_parts: SourceFingerprintParts | None = None,
    ) -> ScenarioBaseline:
        if isinstance(target_type, str):
            target_type = ScenarioTargetType(target_type)
        as_of = _aware(as_of_at)
        self._require_target(ctx, target_type, target_id)

        parts = source_parts or compute_source_fingerprint(
            self._uow,
            ctx,
            target_type=target_type,
            target_id=target_id,
            as_of_at=as_of,
            horizon_days=horizon_days,
            scenario_version_hash=scenario_version_hash,
        )

        projection = self._uow.graph_projection_runs.latest_succeeded(ctx)
        graph_version = (
            getattr(projection, "graph_projection_version", None) if projection else None
        )

        nodes = self._uow.graph_nodes.list_nodes(ctx, limit=100, offset=0, active_at=as_of)
        edges = self._uow.graph_edges.list_edges(ctx, limit=100, offset=0, active_at=as_of)
        findings = self._uow.graph_findings.list_findings(ctx, limit=100, offset=0, active_at=as_of)
        finding_summaries = sorted(
            [
                {
                    "id": f.graph_finding_id,
                    "type": f.finding_type.value
                    if hasattr(f.finding_type, "value")
                    else str(f.finding_type),
                    "severity": f.severity.value
                    if hasattr(f.severity, "value")
                    else str(f.severity),
                    "primary_node_id": f.primary_node_id,
                    "hash": getattr(f, "finding_hash", f.graph_finding_id),
                }
                for f in findings.items
            ],
            key=lambda x: x["id"],
        )
        finding_hashes = [item["hash"] for item in finding_summaries]

        pred_target = PredictionTargetType(target_type.value)
        snapshot = self._extractor.extract(
            ctx,
            pred_target,
            target_id,
            as_of,
            horizon_days=horizon_days,
        )
        feature_values = {
            k: float(v)
            for k, v in (snapshot.feature_values or {}).items()
            if isinstance(v, (int, float)) and float(v) == float(v)
        }
        missingness = {
            k: int(v) for k, v in (snapshot.missingness_indicators or {}).items() if v is not None
        }

        active_model = self._uow.prediction_models.get_active(
            ctx,
            target_definition=TARGET_DEFINITION,
            horizon_days=horizon_days,
            usage_scope=ModelUsageScope.DEMO,
        )
        if active_model is not None:
            model_id = active_model.prediction_model_id
            baseline_version = str(
                getattr(active_model, "model_version", None) or active_model.prediction_model_id
            )
            estimate_hint = EstimateKind.CALIBRATED_PROBABILITY
        else:
            model_id = None
            baseline_version = SCORECARD_VERSION
            estimate_hint = EstimateKind.UNCALIBRATED_SCORE

        warnings = list(snapshot.data_quality_warnings or [])
        if graph_version is None:
            warnings.append("graph_not_current")

        baseline_fingerprint = snapshot_hash(
            {
                # Baseline excludes scenario-version hash so alternative scenarios
                # against the same observed world state remain comparable.
                "graph_projection_version": graph_version,
                "finding_hashes": finding_hashes,
                "feature_hash": snapshot.feature_hash,
                "prediction_baseline_version": baseline_version,
                "as_of_at": as_of.isoformat(),
                "horizon_days": horizon_days,
                "target_type": target_type.value,
                "target_id": target_id,
                "ownership": parts.components.get("ownership"),
                "dependency": parts.components.get("dependency"),
                "availability": parts.components.get("availability"),
                "evidence": parts.components.get("evidence"),
            }
        )

        return ScenarioBaseline(
            target_type=target_type,
            target_id=target_id,
            as_of_at=as_of,
            horizon_days=horizon_days,
            source_fingerprint=parts.fingerprint,
            source_components=dict(parts.components),
            baseline_fingerprint=baseline_fingerprint,
            graph_projection_version=str(graph_version) if graph_version is not None else None,
            graph_node_count=nodes.total,
            graph_edge_count=edges.total,
            finding_hashes=finding_hashes,
            finding_summaries=finding_summaries,
            feature_snapshot_id=snapshot.prediction_feature_snapshot_id,
            feature_values=feature_values,
            missingness=missingness,
            feature_values_hash=snapshot.feature_hash,
            prediction_model_id=model_id,
            prediction_baseline_version=baseline_version,
            estimate_kind_hint=estimate_hint,
            data_quality_warnings=sorted(set(str(w) for w in warnings))[:32],
            data_scope=str(
                snapshot.data_scope.value
                if hasattr(snapshot.data_scope, "value")
                else snapshot.data_scope
            ),
        )

    def _require_target(
        self, ctx: TenantContext, target_type: ScenarioTargetType, target_id: str
    ) -> None:
        from app.services.enterprise.exceptions import EnterpriseNotFoundError

        if target_type == ScenarioTargetType.PROJECT:
            if self._uow.initiatives_projects.get_project(ctx, target_id) is None:
                raise EnterpriseNotFoundError("Project not found for this tenant")
        else:
            if self._uow.initiatives_projects.get_initiative(ctx, target_id) is None:
                raise EnterpriseNotFoundError("Initiative not found for this tenant")
