"""Read-only connector observation API (no sync trigger; no secrets)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v3.dependencies import TenantContextDep, get_unit_of_work
from app.connectors.registry import get_default_registry
from app.db.unit_of_work import UnitOfWork
from app.domain import enterprise_models as dm
from app.services.enterprise.exceptions import EnterpriseNotFoundError

router = APIRouter(prefix="/api/v3", tags=["Connectors"])

_PAGE = Query(default=20, ge=1, le=100)
_OFFSET = Query(default=0, ge=0)


@router.get(
    "/connectors",
    summary="List connector descriptors",
    response_model=list[dict],
)
def list_connectors() -> list[dict]:
    """Public connector capability catalog — never includes credentials."""
    registry = get_default_registry()
    result = []
    for desc in registry.list_descriptors():
        result.append(
            {
                "connector_key": desc.connector_key,
                "display_name": desc.display_name,
                "source_type": desc.source_type.value,
                "operational": desc.capabilities.operational,
                "supports_unauthenticated": desc.capabilities.supports_unauthenticated,
                "supports_webhooks": desc.capabilities.supports_webhooks,
                "streams": [{"name": s.name, "display_name": s.display_name} for s in desc.streams],
                "documentation_notes": desc.documentation_notes,
            }
        )
    return result


@router.get(
    "/data-sources/{data_source_id}/checkpoint-summary",
    summary="Checkpoint summary for a data source",
)
def checkpoint_summary(
    data_source_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
) -> dm.Page[dm.ConnectorCheckpoint]:
    source = uow.data_sources.get_data_source(ctx, data_source_id)
    if source is None:
        raise EnterpriseNotFoundError("Data source not found for this tenant")
    return uow.connector_checkpoints.list_for_source(
        ctx, data_source_id=data_source_id, limit=limit, offset=offset
    )


@router.get(
    "/data-sources/{data_source_id}/freshness",
    summary="Data source freshness summary",
)
def data_source_freshness(
    data_source_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dict:
    source = uow.data_sources.get_data_source(ctx, data_source_id)
    if source is None:
        raise EnterpriseNotFoundError("Data source not found for this tenant")
    # Never expose credential_reference values beyond presence flag.
    return {
        "data_source_id": source.data_source_id,
        "freshness_state": source.freshness_state.value,
        "last_attempted_sync_at": source.last_attempted_sync_at,
        "last_successful_sync_at": source.last_successful_sync_at,
        "last_source_event_time": source.last_source_event_time,
        "last_ingestion_time": source.last_ingestion_time,
        "stale_after_seconds": source.stale_after_seconds,
        "has_credential_reference": bool(source.credential_reference),
        "connector_config_schema_version": source.connector_config_schema_version,
        "connector_config_hash": source.connector_config_hash,
        # Safe non-secret config only
        "connector_config": source.connector_config,
    }


@router.get(
    "/ingestion-runs/{ingestion_run_id}",
    summary="Ingestion run detail",
    response_model=dm.IngestionRun,
)
def get_ingestion_run(
    ingestion_run_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> dm.IngestionRun:
    run = uow.ingestion_runs.get_run(ctx, ingestion_run_id)
    if run is None:
        raise EnterpriseNotFoundError("Ingestion run not found for this tenant")
    return run


@router.get(
    "/ingestion-runs/{ingestion_run_id}/receipts",
    summary="Ingestion receipts for a run",
)
def list_receipts(
    ingestion_run_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
) -> dm.Page[dm.IngestionReceipt]:
    run = uow.ingestion_runs.get_run(ctx, ingestion_run_id)
    if run is None:
        raise EnterpriseNotFoundError("Ingestion run not found for this tenant")
    return uow.ingestion_receipts.list_for_run(
        ctx, ingestion_run_id=ingestion_run_id, limit=limit, offset=offset
    )


@router.get(
    "/ingestion-runs/{ingestion_run_id}/dead-letters",
    summary="Dead letters for a run",
)
def list_dead_letters(
    ingestion_run_id: str,
    ctx: TenantContextDep,
    uow: UnitOfWork = Depends(get_unit_of_work),
    limit: int = _PAGE,
    offset: int = _OFFSET,
) -> dm.Page[dm.IngestionDeadLetter]:
    run = uow.ingestion_runs.get_run(ctx, ingestion_run_id)
    if run is None:
        raise EnterpriseNotFoundError("Ingestion run not found for this tenant")
    return uow.ingestion_dead_letters.list_for_run(
        ctx, ingestion_run_id=ingestion_run_id, limit=limit, offset=offset
    )
