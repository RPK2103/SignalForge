"""Continuous Scenario Intelligence v3 read APIs (Phase 3 Prompt 5).

Read-only endpoints. Mutation and execution remain CLI/service-only because the
tenant header is development context, not authentication.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.v3.dependencies import TenantContextDep, get_unit_of_work
from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_models import Page
from app.domain.scenario_constants import DEFAULT_HORIZON_DAYS
from app.domain.scenario_enums import ComparisonDimension
from app.domain.scenario_models import (
    ScenarioComparisonResult,
    ScenarioDefinition,
    ScenarioHealth,
    ScenarioImpact,
    ScenarioResult,
    ScenarioRun,
    ScenarioTriggerEvent,
    ScenarioVersion,
    ScenarioWatch,
)
from app.services.enterprise.exceptions import (
    EnterpriseNotFoundError,
    EnterpriseValidationError,
)
from app.services.scenarios.orchestration import ScenarioOrchestrationService

router = APIRouter(prefix="/api/v3/scenarios", tags=["Continuous Scenario Intelligence"])

_PAGE = Query(default=20, ge=1, le=100)
_OFFSET = Query(default=0, ge=0)


def _orchestration(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ScenarioOrchestrationService:
    return ScenarioOrchestrationService(uow)


@router.get(
    "/health",
    response_model=ScenarioHealth,
    summary="Scenario intelligence health for the tenant",
)
def scenario_health(
    ctx: TenantContextDep,
    orch: ScenarioOrchestrationService = Depends(_orchestration),
) -> ScenarioHealth:
    return orch.health(ctx)


@router.get(
    "",
    response_model=Page[ScenarioDefinition],
    summary="List scenario definitions",
)
def list_scenarios(
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
) -> Page[ScenarioDefinition]:
    return uow.scenario_definitions.list(
        ctx, limit=limit, offset=offset, target_type=target_type, target_id=target_id
    )


@router.get(
    "/compare",
    response_model=ScenarioComparisonResult,
    summary="Compare compatible scenario runs by an explicit dimension",
)
def compare_scenarios(
    ctx: TenantContextDep,
    run_ids: list[str] = Query(..., min_length=1, max_length=20),
    sort_dimension: str = Query(
        default=ComparisonDimension.AFFECTED_CRITICAL_INITIATIVE_COUNT.value,
        examples=[ComparisonDimension.RISK_SCORE_DELTA.value],
    ),
    descending: bool = Query(default=True),
    orch: ScenarioOrchestrationService = Depends(_orchestration),
) -> ScenarioComparisonResult:
    try:
        return orch.compare(ctx, run_ids, sort_dimension=sort_dimension, descending=descending)
    except ValueError as exc:
        raise EnterpriseValidationError(str(exc)) from exc


@router.get(
    "/watches",
    response_model=Page[ScenarioWatch],
    summary="List scenario watches",
)
def list_watches(
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
    lifecycle_state: str | None = Query(default=None),
) -> Page[ScenarioWatch]:
    return uow.scenario_watches.list(
        ctx, limit=limit, offset=offset, lifecycle_state=lifecycle_state
    )


@router.get(
    "/watches/{watch_id}",
    response_model=ScenarioWatch,
    summary="Get a scenario watch",
)
def get_watch(
    watch_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ScenarioWatch:
    watch = uow.scenario_watches.get(ctx, watch_id)
    if watch is None:
        raise EnterpriseNotFoundError("Scenario watch not found for this tenant")
    return watch


@router.get(
    "/watches/{watch_id}/triggers",
    response_model=Page[ScenarioTriggerEvent],
    summary="List trigger events for a watch",
)
def list_triggers(
    watch_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
) -> Page[ScenarioTriggerEvent]:
    if uow.scenario_watches.get(ctx, watch_id) is None:
        raise EnterpriseNotFoundError("Scenario watch not found for this tenant")
    return uow.scenario_trigger_events.list_for_watch(ctx, watch_id, limit=limit, offset=offset)


@router.get(
    "/runs/{run_id}",
    response_model=ScenarioRun,
    summary="Get a scenario run",
)
def get_run(
    run_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ScenarioRun:
    run = uow.scenario_runs.get(ctx, run_id)
    if run is None:
        raise EnterpriseNotFoundError("Scenario run not found for this tenant")
    return run


@router.get(
    "/runs/{run_id}/result",
    response_model=ScenarioResult,
    summary="Get an immutable scenario result",
)
def get_run_result(
    run_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ScenarioResult:
    if uow.scenario_runs.get(ctx, run_id) is None:
        raise EnterpriseNotFoundError("Scenario run not found for this tenant")
    result = uow.scenario_results.get_by_run(ctx, run_id)
    if result is None:
        raise EnterpriseNotFoundError("Scenario result not found for this tenant")
    return result


@router.get(
    "/runs/{run_id}/impacts",
    response_model=Page[ScenarioImpact],
    summary="List bounded impacts for a scenario run",
)
def list_impacts(
    run_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
) -> Page[ScenarioImpact]:
    if uow.scenario_runs.get(ctx, run_id) is None:
        raise EnterpriseNotFoundError("Scenario run not found for this tenant")
    return uow.scenario_impacts.list_for_run(ctx, run_id, limit=limit, offset=offset)


@router.get(
    "/{scenario_id}",
    response_model=ScenarioDefinition,
    summary="Get a scenario definition",
)
def get_scenario(
    scenario_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ScenarioDefinition:
    definition = uow.scenario_definitions.get(ctx, scenario_id)
    if definition is None:
        raise EnterpriseNotFoundError("Scenario definition not found for this tenant")
    return definition


@router.get(
    "/{scenario_id}/versions",
    response_model=Page[ScenarioVersion],
    summary="List immutable scenario versions",
)
def list_versions(
    scenario_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
) -> Page[ScenarioVersion]:
    if uow.scenario_definitions.get(ctx, scenario_id) is None:
        raise EnterpriseNotFoundError("Scenario definition not found for this tenant")
    return uow.scenario_versions.list_for_definition(ctx, scenario_id, limit=limit, offset=offset)


@router.get(
    "/{scenario_id}/runs",
    response_model=Page[ScenarioRun],
    summary="List scenario runs for a definition",
)
def list_runs(
    scenario_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
) -> Page[ScenarioRun]:
    if uow.scenario_definitions.get(ctx, scenario_id) is None:
        raise EnterpriseNotFoundError("Scenario definition not found for this tenant")
    return uow.scenario_runs.list_for_definition(ctx, scenario_id, limit=limit, offset=offset)


# Silence unused import in OpenAPI examples context
_ = DEFAULT_HORIZON_DAYS
_ = datetime
