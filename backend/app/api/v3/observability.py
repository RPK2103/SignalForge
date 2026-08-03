"""Protected observability & AI-quality v3 routes (Phase 3 Prompt 8).

Every route is authenticated (middleware), tenant-resolved, and permission-gated
by ``require_permission`` (deny-by-default). The application services re-check the
same permission, so a direct service call without context also fails closed.

No route is public. Responses carry only bounded, safe fields — never raw
prompts, evidence packages, tokens or high-cardinality identifiers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.persistence_dependencies import get_db_session
from app.api.v3.dependencies import require_permission
from app.db.unit_of_work import UnitOfWork
from app.security.context import SecurityContext
from app.security.enums import Permission
from app.services.observability.ai_quality_service import AiQualityService
from app.services.observability.observability_service import ObservabilityService

router = APIRouter(prefix="/api/v3/observability", tags=["Observability"])

_READ = require_permission(Permission.OBSERVABILITY_READ)
_MANAGE = require_permission(Permission.OBSERVABILITY_MANAGE)
_AI_READ = require_permission(Permission.AI_QUALITY_READ)
_AI_EVAL = require_permission(Permission.AI_QUALITY_EVALUATE)


def get_observability_service(session: Session = Depends(get_db_session)) -> ObservabilityService:
    return ObservabilityService(UnitOfWork(session))


def get_ai_quality_service(session: Session = Depends(get_db_session)) -> AiQualityService:
    return AiQualityService(UnitOfWork(session))


@router.get("/summary")
def get_summary(
    context: SecurityContext = Depends(_READ),
    service: ObservabilityService = Depends(get_observability_service),
) -> dict:
    return service.get_summary(context)


@router.get("/metrics")
def list_metrics(
    context: SecurityContext = Depends(_READ),
    metric_name: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    service: ObservabilityService = Depends(get_observability_service),
) -> list[dict]:
    rows = service.list_metrics(context, metric_name=metric_name, limit=limit)
    return [r.model_dump(mode="json") for r in rows]


@router.get("/freshness")
def get_freshness(
    context: SecurityContext = Depends(_READ),
    service: ObservabilityService = Depends(get_observability_service),
) -> list[dict]:
    return service.get_freshness(context)


@router.get("/slo-definitions")
def list_slo_definitions(
    context: SecurityContext = Depends(_READ),
    service: ObservabilityService = Depends(get_observability_service),
) -> list[dict]:
    return [r.model_dump(mode="json") for r in service.list_slo_definitions(context)]


@router.get("/slo-evaluations")
def list_slo_evaluations(
    context: SecurityContext = Depends(_READ),
    slo_key: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    service: ObservabilityService = Depends(get_observability_service),
) -> list[dict]:
    rows = service.list_slo_evaluations(context, slo_key=slo_key, limit=limit)
    return [r.model_dump(mode="json") for r in rows]


@router.get("/alerts")
def list_alerts(
    context: SecurityContext = Depends(_READ),
    state: str | None = Query(default=None, pattern="^(open|acknowledged|resolved)$"),
    limit: int = Query(default=50, ge=1, le=100),
    service: ObservabilityService = Depends(get_observability_service),
) -> list[dict]:
    rows = service.list_alerts(context, state=state, limit=limit)
    return [r.model_dump(mode="json") for r in rows]


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    context: SecurityContext = Depends(_MANAGE),
    service: ObservabilityService = Depends(get_observability_service),
) -> dict:
    record = service.acknowledge_alert(context, alert_id=alert_id)
    return record.model_dump(mode="json")


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: str,
    context: SecurityContext = Depends(_MANAGE),
    service: ObservabilityService = Depends(get_observability_service),
) -> dict:
    record = service.resolve_alert(context, alert_id=alert_id)
    return record.model_dump(mode="json")


@router.get("/ai-quality/runs")
def list_ai_runs(
    context: SecurityContext = Depends(_AI_READ),
    limit: int = Query(default=50, ge=1, le=100),
    service: AiQualityService = Depends(get_ai_quality_service),
) -> list[dict]:
    return [r.model_dump(mode="json") for r in service.list_runs(context, limit=limit)]


@router.get("/ai-quality/runs/{run_id}")
def get_ai_run(
    run_id: str,
    context: SecurityContext = Depends(_AI_READ),
    service: AiQualityService = Depends(get_ai_quality_service),
) -> dict:
    result = service.get_run(context, run_id=run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return result


@router.post("/ai-quality/evaluate")
def run_ai_evaluation(
    context: SecurityContext = Depends(_AI_EVAL),
    service: AiQualityService = Depends(get_ai_quality_service),
) -> dict:
    run = service.run_release_evaluation(context)
    return run.model_dump(mode="json")


@router.get("/prediction-quality")
def list_prediction_quality(
    context: SecurityContext = Depends(_READ),
    model_version: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    service: ObservabilityService = Depends(get_observability_service),
) -> list[dict]:
    rows = service.list_prediction_quality(context, model_version=model_version, limit=limit)
    return [r.model_dump(mode="json") for r in rows]
