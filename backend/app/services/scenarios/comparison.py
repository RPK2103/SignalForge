"""Deterministic scenario comparison — no opaque aggregate ranking."""

from __future__ import annotations

from datetime import datetime

from app.db.unit_of_work import UnitOfWork
from app.domain.scenario_constants import MAX_COMPARISON_RUNS
from app.domain.scenario_enums import ComparisonDimension, EstimateComparability
from app.domain.scenario_models import (
    ScenarioComparisonDimensionValue,
    ScenarioComparisonResult,
    ScenarioResult,
    ScenarioRun,
)
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseNotFoundError, EnterpriseValidationError

_DIMENSION_EXTRACTORS = {
    ComparisonDimension.AFFECTED_PROJECT_COUNT: lambda r: r.affected_project_count,
    ComparisonDimension.AFFECTED_INITIATIVE_COUNT: lambda r: r.affected_initiative_count,
    ComparisonDimension.AFFECTED_CRITICAL_INITIATIVE_COUNT: lambda r: (
        r.affected_critical_initiative_count
    ),
    ComparisonDimension.GRAPH_FINDINGS_ADDED: lambda r: r.findings_added_count,
    ComparisonDimension.GRAPH_FINDINGS_WORSENED: lambda r: r.findings_worsened_count,
    ComparisonDimension.OWNERSHIP_CONCENTRATION_CHANGE: lambda r: float(
        (r.delta_summary or {}).get("ownership_concentration_delta") or 0.0
    ),
    ComparisonDimension.CAPABILITY_CONCENTRATION_CHANGE: lambda r: float(
        (r.delta_summary or {}).get("capability_concentration_delta") or 0.0
    ),
    ComparisonDimension.DEPENDENCY_DELAY: lambda r: float(
        (r.delta_summary or {}).get("dependency_delay_days") or 0.0
    ),
    ComparisonDimension.RISK_SCORE_DELTA: lambda r: r.risk_score_delta,
    ComparisonDimension.PROBABILITY_DELTA: lambda r: r.probability_delta,
    ComparisonDimension.DATA_QUALITY_DEGRADATION: lambda r: len(r.data_quality_warnings or []),
}


class ScenarioComparisonService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def compare(
        self,
        ctx: TenantContext,
        run_ids: list[str],
        *,
        sort_dimension: ComparisonDimension | str,
        descending: bool = True,
    ) -> ScenarioComparisonResult:
        if isinstance(sort_dimension, str):
            try:
                sort_dimension = ComparisonDimension(sort_dimension)
            except ValueError as exc:
                raise EnterpriseValidationError(
                    f"Unsupported comparison dimension: {sort_dimension}"
                ) from exc
        if not run_ids:
            raise EnterpriseValidationError("At least one run_id is required")
        if len(run_ids) > MAX_COMPARISON_RUNS:
            raise EnterpriseValidationError(f"At most {MAX_COMPARISON_RUNS} runs may be compared")

        runs: list[ScenarioRun] = []
        results: list[ScenarioResult] = []
        for run_id in run_ids:
            run = self._uow.scenario_runs.get(ctx, run_id)
            if run is None:
                raise EnterpriseNotFoundError("Scenario run not found for this tenant")
            result = self._uow.scenario_results.get_by_run(ctx, run_id)
            if result is None:
                raise EnterpriseNotFoundError("Scenario result not found for this tenant")
            runs.append(run)
            results.append(result)

        self._assert_compatible(runs, results)

        estimate_comp = results[0].estimate_comparability
        dimensions: list[ScenarioComparisonDimensionValue] = []
        for dim in ComparisonDimension:
            values: dict[str, float | int | None] = {}
            for result in results:
                if (
                    dim
                    in {
                        ComparisonDimension.RISK_SCORE_DELTA,
                        ComparisonDimension.PROBABILITY_DELTA,
                    }
                    and result.estimate_comparability
                    == EstimateComparability.INCOMPARABLE_ESTIMATE_KIND
                ):
                    values[result.scenario_run_id] = None
                else:
                    values[result.scenario_run_id] = _DIMENSION_EXTRACTORS[dim](result)
            dimensions.append(
                ScenarioComparisonDimensionValue(dimension=dim, values_by_run_id=values)
            )

        sort_values = {r.scenario_run_id: _DIMENSION_EXTRACTORS[sort_dimension](r) for r in results}

        def sort_key(run_id: str) -> tuple:
            value = sort_values.get(run_id)
            missing = value is None
            numeric = float(value) if value is not None else 0.0
            # Missing values sort last regardless of direction.
            return (missing, -numeric if descending else numeric, run_id)

        ordered = sorted([r.scenario_run_id for r in results], key=sort_key)
        warnings: list[str] = []
        if estimate_comp == EstimateComparability.INCOMPARABLE_ESTIMATE_KIND:
            warnings.append("estimate_kinds_incomparable")
        if sort_dimension == ComparisonDimension.PROBABILITY_DELTA and any(
            r.probability_delta is None for r in results
        ):
            warnings.append("probability_delta_unavailable_for_some_runs")
        if sort_dimension == ComparisonDimension.RISK_SCORE_DELTA and any(
            r.risk_score_delta is None for r in results
        ):
            warnings.append("risk_score_delta_unavailable_for_some_runs")

        return ScenarioComparisonResult(
            tenant_id=ctx.tenant_id,
            target_type=runs[0].target_type,
            target_id=runs[0].target_id,
            as_of_at=runs[0].as_of_at,
            horizon_days=runs[0].horizon_days,
            estimate_comparability=estimate_comp,
            run_ids=[r.scenario_run_id for r in runs],
            dimensions=dimensions,
            ordered_run_ids=ordered,
            sort_dimension=sort_dimension,
            warnings=warnings,
            comparable=estimate_comp
            in {
                EstimateComparability.COMPARABLE_PROBABILITY,
                EstimateComparability.COMPARABLE_SCORE,
            },
        )

    def _assert_compatible(self, runs: list[ScenarioRun], results: list[ScenarioResult]) -> None:
        first = runs[0]
        for run in runs[1:]:
            if run.target_type != first.target_type or run.target_id != first.target_id:
                raise EnterpriseValidationError("Compared runs must share the same target")
            if _norm_dt(run.as_of_at) != _norm_dt(first.as_of_at):
                raise EnterpriseValidationError("Compared runs must share the same as_of_at")
            if run.horizon_days != first.horizon_days:
                raise EnterpriseValidationError("Compared runs must share the same horizon")
            if run.baseline_fingerprint != first.baseline_fingerprint:
                raise EnterpriseValidationError(
                    "Compared runs must share a compatible baseline fingerprint"
                )
        kinds = {r.estimate_comparability for r in results}
        # Allow comparison listing even if incomparable; numeric deltas stay null.
        if len({r.baseline_estimate_kind for r in results}) > 1:
            # Still allowed to return incomparable_estimate_kind payload.
            return
        _ = kinds


def _norm_dt(value: datetime) -> str:
    return value.astimezone().isoformat() if value.tzinfo else value.isoformat()
