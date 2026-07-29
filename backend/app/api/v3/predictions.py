"""Delivery Prediction v3 read APIs (Phase 3 Prompt 4).

Read-oriented endpoints only — no public training or promotion. Tenant header is
development context, not authentication.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.api.v3.dependencies import TenantContextDep, get_unit_of_work
from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_models import Page
from app.domain.prediction_constants import DEFAULT_HORIZON_DAYS, SUPPORTED_HORIZONS
from app.domain.prediction_enums import PredictionTargetType, VerificationStatus
from app.domain.prediction_models import (
    DeliveryOutcome,
    DeliveryPrediction,
    DeliveryPredictionBundle,
    PredictionDataHealth,
    PredictionModel,
    PredictionModelEvaluation,
    PredictionRun,
    validate_horizon,
)
from app.services.enterprise.exceptions import (
    EnterpriseNotFoundError,
    EnterpriseValidationError,
)
from app.services.prediction.orchestration import PredictionOrchestrationService

router = APIRouter(prefix="/api/v3/predictions", tags=["Delivery Prediction"])

_PAGE = Query(default=20, ge=1, le=100)
_OFFSET = Query(default=0, ge=0)
_HORIZON = Query(
    default=DEFAULT_HORIZON_DAYS,
    description="Prediction horizon in days",
    examples=[90],
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _orchestration(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PredictionOrchestrationService:
    return PredictionOrchestrationService(uow)


def _require_horizon(horizon_days: int) -> int:
    try:
        return validate_horizon(horizon_days)
    except ValueError as exc:
        raise EnterpriseValidationError(str(exc)) from exc


def _require_project(uow: UnitOfWork, ctx: TenantContextDep, project_id: str) -> None:
    project = uow.initiatives_projects.get_project(ctx, project_id)
    if project is None:
        raise EnterpriseNotFoundError("Project not found for this tenant")


def _require_initiative(uow: UnitOfWork, ctx: TenantContextDep, initiative_id: str) -> None:
    initiative = uow.initiatives_projects.get_initiative(ctx, initiative_id)
    if initiative is None:
        raise EnterpriseNotFoundError("Initiative not found for this tenant")


def _require_model(uow: UnitOfWork, ctx: TenantContextDep, model_id: str) -> PredictionModel:
    model = uow.prediction_models.get(ctx, model_id)
    if model is None:
        raise EnterpriseNotFoundError("Prediction model not found for this tenant")
    return model


def _bundle_for_prediction(
    uow: UnitOfWork,
    ctx: TenantContextDep,
    prediction: DeliveryPrediction,
) -> DeliveryPredictionBundle:
    factors = uow.prediction_factors.list_for_prediction(ctx, prediction.delivery_prediction_id)
    run = uow.prediction_runs.get(ctx, prediction.prediction_run_id)
    return DeliveryPredictionBundle(prediction=prediction, factors=factors, run=run)


def _predict_or_latest(
    *,
    uow: UnitOfWork,
    ctx: TenantContextDep,
    orch: PredictionOrchestrationService,
    target_type: PredictionTargetType,
    target_id: str,
    horizon_days: int,
    as_of: datetime | None,
) -> DeliveryPredictionBundle:
    horizon_days = _require_horizon(horizon_days)

    if as_of is None:
        latest = uow.delivery_predictions.latest_for_target(ctx, target_type.value, target_id)
        if latest is not None and latest.horizon_days == horizon_days:
            return _bundle_for_prediction(uow, ctx, latest)
        when = _utcnow()
    else:
        when = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)

    bundle = orch.predict(
        ctx,
        target_type,
        target_id,
        as_of_at=when,
        horizon_days=horizon_days,
    )
    uow.commit()
    return bundle


@router.get(
    "/projects/{project_id}",
    response_model=DeliveryPredictionBundle,
    summary="Predict or return latest project delivery prediction",
    responses={
        404: {"description": "Not found for tenant"},
        422: {"description": "Unsupported horizon"},
        400: {"description": "Missing tenant context"},
    },
    openapi_extra={
        "examples": {
            "default": {
                "summary": "90-day project prediction",
                "value": {"horizon_days": 90},
            }
        }
    },
)
def predict_project(
    project_id: str,
    ctx: TenantContextDep,
    horizon_days: int = _HORIZON,
    as_of: datetime | None = Query(
        default=None,
        description="As-of timestamp (ISO-8601). Defaults to utcnow when omitted "
        "and no matching latest prediction exists.",
        examples=["2025-06-01T00:00:00Z"],
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
    orch: PredictionOrchestrationService = Depends(_orchestration),
) -> DeliveryPredictionBundle:
    """Return the latest matching prediction, or run inference for the project."""
    _require_project(uow, ctx, project_id)
    return _predict_or_latest(
        uow=uow,
        ctx=ctx,
        orch=orch,
        target_type=PredictionTargetType.PROJECT,
        target_id=project_id,
        horizon_days=horizon_days,
        as_of=as_of,
    )


@router.get(
    "/projects/{project_id}/history",
    response_model=Page[DeliveryPrediction],
    summary="Paginated project prediction history",
    responses={404: {"description": "Not found for tenant"}},
)
def project_prediction_history(
    project_id: str,
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Page[DeliveryPrediction]:
    _require_project(uow, ctx, project_id)
    return uow.delivery_predictions.list_for_target(
        ctx,
        PredictionTargetType.PROJECT.value,
        project_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/initiatives/{initiative_id}",
    response_model=DeliveryPredictionBundle,
    summary="Predict or return latest initiative delivery prediction",
    responses={
        404: {"description": "Not found for tenant"},
        422: {"description": "Unsupported horizon"},
    },
)
def predict_initiative(
    initiative_id: str,
    ctx: TenantContextDep,
    horizon_days: int = _HORIZON,
    as_of: datetime | None = Query(
        default=None,
        description="As-of timestamp (ISO-8601). Defaults to utcnow when omitted "
        "and no matching latest prediction exists.",
        examples=["2025-06-01T00:00:00Z"],
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
    orch: PredictionOrchestrationService = Depends(_orchestration),
) -> DeliveryPredictionBundle:
    _require_initiative(uow, ctx, initiative_id)
    return _predict_or_latest(
        uow=uow,
        ctx=ctx,
        orch=orch,
        target_type=PredictionTargetType.INITIATIVE,
        target_id=initiative_id,
        horizon_days=horizon_days,
        as_of=as_of,
    )


@router.get(
    "/initiatives/{initiative_id}/history",
    response_model=Page[DeliveryPrediction],
    summary="Paginated initiative prediction history",
    responses={404: {"description": "Not found for tenant"}},
)
def initiative_prediction_history(
    initiative_id: str,
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Page[DeliveryPrediction]:
    _require_initiative(uow, ctx, initiative_id)
    return uow.delivery_predictions.list_for_target(
        ctx,
        PredictionTargetType.INITIATIVE.value,
        initiative_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/models",
    response_model=Page[PredictionModel],
    summary="List prediction models",
)
def list_models(
    ctx: TenantContextDep,
    horizon_days: int | None = Query(default=None, examples=[90]),
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Page[PredictionModel]:
    if horizon_days is not None:
        _require_horizon(horizon_days)
    return uow.prediction_models.list(ctx, horizon_days=horizon_days, limit=limit, offset=offset)


@router.get(
    "/models/{model_id}",
    response_model=PredictionModel,
    summary="Get prediction model",
    responses={404: {"description": "Not found for tenant"}},
)
def get_model(
    model_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PredictionModel:
    return _require_model(uow, ctx, model_id)


@router.get(
    "/models/{model_id}/evaluation",
    response_model=Page[PredictionModelEvaluation],
    summary="Evaluations for a model (latest first)",
    responses={404: {"description": "Not found for tenant"}},
)
def model_evaluation(
    model_id: str,
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Page[PredictionModelEvaluation]:
    """Paginated evaluations ordered by evaluated_at desc (latest first)."""
    _require_model(uow, ctx, model_id)
    return uow.prediction_evaluations.list_for_model(ctx, model_id, limit=limit, offset=offset)


@router.get(
    "/evaluations",
    response_model=Page[PredictionModelEvaluation],
    summary="List model evaluations",
)
def list_evaluations(
    ctx: TenantContextDep,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Page[PredictionModelEvaluation]:
    return uow.prediction_evaluations.list(ctx, limit=limit, offset=offset)


@router.get(
    "/runs",
    response_model=Page[PredictionRun],
    summary="List prediction runs",
)
def list_runs(
    ctx: TenantContextDep,
    target_type: PredictionTargetType | None = None,
    target_id: str | None = Query(default=None, max_length=64),
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Page[PredictionRun]:
    return uow.prediction_runs.list(
        ctx,
        target_type=target_type.value if target_type else None,
        target_id=target_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/data-health",
    response_model=PredictionDataHealth,
    summary="Prediction data sufficiency health",
)
def data_health(
    ctx: TenantContextDep,
    orch: PredictionOrchestrationService = Depends(_orchestration),
) -> PredictionDataHealth:
    return orch.data_health(ctx)


@router.get(
    "/outcomes",
    response_model=Page[DeliveryOutcome],
    summary="List delivery outcomes",
)
def list_outcomes(
    ctx: TenantContextDep,
    verification_status: VerificationStatus | None = None,
    limit: int = _PAGE,
    offset: int = _OFFSET,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Page[DeliveryOutcome]:
    return uow.delivery_outcomes.list_outcomes(
        ctx,
        verification_status=verification_status,
        limit=limit,
        offset=offset,
    )


# Keep supported horizons discoverable for OpenAPI consumers.
SUPPORTED_HORIZON_DAYS = sorted(SUPPORTED_HORIZONS)
