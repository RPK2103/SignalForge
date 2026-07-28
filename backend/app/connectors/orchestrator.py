"""Ingestion orchestrator — fetch outside TX, persist per-event outcomes."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.connectors.config import hash_connector_config, validate_connector_config
from app.connectors.credentials import ChainedCredentialResolver, CredentialResolver
from app.connectors.errors import ConnectorError, sanitize_error_message
from app.connectors.freshness import compute_freshness
from app.connectors.projections import ProjectionService
from app.connectors.protocol import (
    Connector,
    ConnectorCheckpointCursor,
    ConnectorContext,
    ConnectorRequest,
    NormalizedConnectorEvent,
)
from app.connectors.registry import ConnectorRegistry, get_default_registry
from app.db.unit_of_work import UnitOfWork
from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import (
    ConnectorErrorCategory,
    DataSourceStatus,
    DeadLetterReplayState,
    EvidenceSignalType,
    FreshnessState,
    IngestionErrorCategory,
    IngestionReceiptOutcome,
    IngestionRunStatus,
    IngestionRunType,
    PermissionClassification,
)
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseNotFoundError, EnterpriseValidationError
from app.services.persistence.snapshot_service import snapshot_hash

_logger = logging.getLogger("signalforge.connectors.orchestrator")

_SECRET_PAYLOAD_KEYS = frozenset(
    {
        "token",
        "password",
        "secret",
        "api_key",
        "authorization",
        "private_key",
        "access_token",
        "refresh_token",
        "connection_string",
        "bearer",
    }
)

_EVENT_TO_SIGNAL: dict[str, EvidenceSignalType] = {
    "github.repository.snapshot": EvidenceSignalType.REPOSITORY_SNAPSHOT,
    "github.pull_request.snapshot": EvidenceSignalType.PULL_REQUEST,
    "github.pull_request_review.snapshot": EvidenceSignalType.CODE_REVIEW,
    "github.issue.snapshot": EvidenceSignalType.ISSUE_SNAPSHOT,
    "github.release.snapshot": EvidenceSignalType.RELEASE_SNAPSHOT,
}

_EVENT_TO_SUBJECT = {
    "github.repository.snapshot": ("repository",),
    "github.pull_request.snapshot": ("pull_request",),
    "github.pull_request_review.snapshot": ("pull_request",),
    "github.issue.snapshot": ("work_item",),
    "github.release.snapshot": ("repository",),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize SQLite-naive and aware datetimes for safe comparison."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def redact_payload(payload: dict[str, Any] | None, *, max_chars: int = 4096) -> dict[str, Any]:
    """Bound and redact secret-like keys from dead-letter payloads."""
    if not payload:
        return {}

    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for key, value in obj.items():
                if str(key).lower() in _SECRET_PAYLOAD_KEYS or "token" in str(key).lower():
                    out[str(key)] = "[redacted]"
                else:
                    out[str(key)] = _walk(value)
            return out
        if isinstance(obj, list):
            return [_walk(item) for item in obj[:50]]
        if isinstance(obj, str) and len(obj) > 512:
            return obj[:512] + "…"
        return obj

    redacted = _walk(payload)
    from app.services.persistence.snapshot_service import canonical_json

    encoded = canonical_json(redacted)
    if len(encoded) > max_chars:
        return {"_truncated": True, "keys": list(payload.keys())[:40]}
    return redacted


@dataclass
class RunCounters:
    fetched: int = 0
    normalized: int = 0
    created: int = 0
    deduplicated: int = 0
    projected: int = 0
    skipped: int = 0
    dead_lettered: int = 0
    retried: int = 0
    requests: int = 0
    rate_limit_waits: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "normalized": self.normalized,
            "created": self.created,
            "deduplicated": self.deduplicated,
            "projected": self.projected,
            "skipped": self.skipped,
            "dead_lettered": self.dead_lettered,
            "retried": self.retried,
            "requests": self.requests,
            "rate_limit_waits": self.rate_limit_waits,
        }


@dataclass
class SyncResult:
    ingestion_run_id: str
    status: IngestionRunStatus
    counters: RunCounters = field(default_factory=RunCounters)
    streams: list[str] = field(default_factory=list)
    error_summary: str | None = None
    freshness_state: FreshnessState = FreshnessState.NEVER_SYNCED


class IngestionOrchestrator:
    """Coordinates connector fetch → normalize → evidence → receipt → projection → checkpoint.

    HTTP is performed outside database transactions.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        registry: ConnectorRegistry | None = None,
        credential_resolver: CredentialResolver | None = None,
        connector: Connector | None = None,
    ) -> None:
        self._uow = uow
        self._registry = registry or get_default_registry()
        self._credentials = credential_resolver or ChainedCredentialResolver()
        self._connector_override = connector
        self._projections = ProjectionService(uow)

    def sync_data_source(
        self,
        ctx: TenantContext,
        data_source_id: str,
        *,
        run_type: IngestionRunType = IngestionRunType.INCREMENTAL,
        maximum_pages: int | None = None,
        streams: list[str] | None = None,
        correlation_id: str | None = None,
    ) -> SyncResult:
        correlation = correlation_id or str(uuid.uuid4())
        source = self._uow.data_sources.get_data_source(ctx, data_source_id)
        if source is None:
            raise EnterpriseNotFoundError("Data source not found for this tenant")
        if not source.connector_config:
            raise EnterpriseValidationError("Data source has no connector_config")

        config = validate_connector_config(source.source_type.value, source.connector_config)
        config_hash = hash_connector_config(config)
        if source.connector_config_hash != config_hash:
            source = source.model_copy(
                update={
                    "connector_config": config,
                    "connector_config_schema_version": "1",
                    "connector_config_hash": config_hash,
                }
            )
            self._uow.data_sources.update_data_source(ctx, source)
            self._uow.commit()

        resolved = self._credentials.resolve(source.credential_reference)
        connector = self._connector_override or self._registry.get(source.source_type.value)

        started_at = _utcnow()
        run = dm.IngestionRun(
            ingestion_run_id=build_entity_id(
                "run", ctx.tenant_id, data_source_id, correlation, started_at.isoformat()
            ),
            tenant_id=ctx.tenant_id,
            data_source_id=data_source_id,
            run_type=run_type,
            status=IngestionRunStatus.RUNNING,
            started_at=started_at,
        )
        self._uow.ingestion_runs.add_run(ctx, run)
        source = source.model_copy(update={"last_attempted_sync_at": started_at})
        self._uow.data_sources.update_data_source(ctx, source)
        self._uow.commit()

        _logger.info(
            "connector.run.started tenant_id=%s data_source_id=%s ingestion_run_id=%s "
            "connector=%s correlation_id=%s",
            ctx.tenant_id,
            data_source_id,
            run.ingestion_run_id,
            source.source_type.value,
            correlation,
        )

        counters = RunCounters()
        enabled = streams or list(config.get("enabled_streams") or [])
        context = ConnectorContext(
            tenant=ctx,
            data_source_id=data_source_id,
            correlation_id=correlation,
            credential_token=resolved.token,
            max_pages=maximum_pages or config.get("maximum_pages"),
        )

        fatal_error: ConnectorError | None = None
        max_source_event_time: datetime | None = _as_utc(source.last_source_event_time)
        try:
            for stream_name in enabled:
                stream_hw = self._sync_stream(
                    ctx,
                    connector=connector,
                    config=config,
                    context=context,
                    run=run,
                    stream_name=stream_name,
                    counters=counters,
                    page_size=int(config.get("page_size") or 30),
                    overlap_seconds=int(config.get("overlap_seconds") or 60),
                )
                stream_hw = _as_utc(stream_hw)
                if stream_hw is not None and (
                    max_source_event_time is None or stream_hw > max_source_event_time
                ):
                    max_source_event_time = stream_hw
        except ConnectorError as exc:
            fatal_error = exc
            _logger.info(
                "connector.run.failed tenant_id=%s ingestion_run_id=%s category=%s "
                "correlation_id=%s",
                ctx.tenant_id,
                run.ingestion_run_id,
                exc.category.value,
                correlation,
            )

        # Determine terminal status
        if fatal_error is not None and counters.fetched == 0 and counters.dead_lettered == 0:
            status = IngestionRunStatus.FAILED
            error_category = _map_ingestion_error(fatal_error.category)
            error_summary = fatal_error.safe_message
        elif counters.dead_lettered > 0 or fatal_error is not None:
            status = IngestionRunStatus.PARTIAL
            error_category = (
                _map_ingestion_error(fatal_error.category)
                if fatal_error
                else IngestionErrorCategory.VALIDATION
            )
            error_summary = (
                fatal_error.safe_message if fatal_error else "Run completed with dead letters"
            )
        else:
            status = IngestionRunStatus.SUCCEEDED
            error_category = IngestionErrorCategory.NONE
            error_summary = None

        completed_at = _utcnow()
        updated_run = run.model_copy(
            update={
                "status": status,
                "completed_at": completed_at,
                "records_read": counters.fetched,
                "records_written": counters.created,
                "records_skipped": counters.skipped + counters.deduplicated,
                "records_normalized": counters.normalized,
                "records_created": counters.created,
                "records_deduplicated": counters.deduplicated,
                "records_projected": counters.projected,
                "records_dead_lettered": counters.dead_lettered,
                "records_retried": counters.retried,
                "request_count": counters.requests,
                "rate_limit_waits": counters.rate_limit_waits,
                "error_category": error_category,
                "error_summary": sanitize_error_message(error_summary) if error_summary else None,
            }
        )
        self._uow.ingestion_runs.update_run(ctx, updated_run)

        last_success = source.last_successful_sync_at
        if status in {IngestionRunStatus.SUCCEEDED, IngestionRunStatus.PARTIAL}:
            last_success = completed_at
        freshness = compute_freshness(
            last_successful_sync_at=last_success,
            last_attempted_sync_at=completed_at,
            failed=status == IngestionRunStatus.FAILED,
            stale_after_seconds=source.stale_after_seconds,
            now=completed_at,
        )
        source_updates: dict[str, Any] = {
            "last_attempted_sync_at": completed_at,
            "last_successful_sync_at": last_success,
            "last_ingestion_time": completed_at,
            "freshness_state": freshness,
            "status": (
                DataSourceStatus.ERROR
                if status == IngestionRunStatus.FAILED
                else DataSourceStatus.CONNECTED
            ),
        }
        if status in {IngestionRunStatus.SUCCEEDED, IngestionRunStatus.PARTIAL}:
            source_updates["last_source_event_time"] = max_source_event_time
        source = source.model_copy(update=source_updates)
        self._uow.data_sources.update_data_source(ctx, source)
        self._uow.commit()

        _logger.info(
            "connector.run.completed tenant_id=%s ingestion_run_id=%s status=%s "
            "fetched=%d created=%d deduplicated=%d dead_lettered=%d correlation_id=%s",
            ctx.tenant_id,
            run.ingestion_run_id,
            status.value,
            counters.fetched,
            counters.created,
            counters.deduplicated,
            counters.dead_lettered,
            correlation,
        )
        return SyncResult(
            ingestion_run_id=run.ingestion_run_id,
            status=status,
            counters=counters,
            streams=enabled,
            error_summary=error_summary,
            freshness_state=freshness,
        )

    def _sync_stream(
        self,
        ctx: TenantContext,
        *,
        connector: Connector,
        config: dict[str, Any],
        context: ConnectorContext,
        run: dm.IngestionRun,
        stream_name: str,
        counters: RunCounters,
        page_size: int,
        overlap_seconds: int,
    ) -> datetime | None:
        existing = self._uow.connector_checkpoints.get(
            ctx, data_source_id=run.data_source_id, stream_name=stream_name
        )
        _logger.info(
            "connector.checkpoint.loaded tenant_id=%s data_source_id=%s stream=%s present=%s",
            ctx.tenant_id,
            run.data_source_id,
            stream_name,
            existing is not None,
        )
        checkpoint_cursor = None
        expected_version = None
        if existing is not None:
            checkpoint_cursor = ConnectorCheckpointCursor(
                schema_version=existing.cursor_schema_version,
                payload=dict(existing.cursor_payload or {}),
                high_watermark_time=existing.high_watermark_time,
                high_watermark_source_id=existing.high_watermark_source_id,
                etag=existing.etag,
            )
            expected_version = existing.version

        pages_fetched = 0
        has_more = True
        last_hw: datetime | None = _as_utc(
            checkpoint_cursor.high_watermark_time if checkpoint_cursor else None
        )
        while has_more:
            request = ConnectorRequest(
                stream_name=stream_name,
                page_size=page_size,
                checkpoint=checkpoint_cursor,
                overlap_seconds=overlap_seconds,
                maximum_pages=context.max_pages,
            )
            # Provider fetch OUTSIDE any write transaction assumptions.
            page = connector.fetch_page(context, config, request)
            counters.requests += page.request_count
            counters.fetched += len(page.normalized_events)
            counters.normalized += len(page.normalized_events)
            pages_fetched += 1

            for event in page.normalized_events:
                self._persist_event(ctx, run=run, event=event, counters=counters)
                event_time = _as_utc(event.event_time)
                if event_time is not None and (last_hw is None or event_time > last_hw):
                    last_hw = event_time

            # Advance checkpoint only after every record has a durable outcome.
            if page.next_checkpoint is not None:
                self._advance_checkpoint(
                    ctx,
                    data_source_id=run.data_source_id,
                    stream_name=stream_name,
                    cursor=page.next_checkpoint,
                    run_id=run.ingestion_run_id,
                    expected_version=expected_version,
                )
                refreshed = self._uow.connector_checkpoints.get(
                    ctx, data_source_id=run.data_source_id, stream_name=stream_name
                )
                expected_version = refreshed.version if refreshed else None
                checkpoint_cursor = page.next_checkpoint
                page_hw = _as_utc(page.next_checkpoint.high_watermark_time)
                if page_hw is not None and (last_hw is None or page_hw > last_hw):
                    last_hw = page_hw

            has_more = page.has_more
            if context.max_pages is not None and pages_fetched >= context.max_pages:
                break
        return last_hw

    def _persist_event(
        self,
        ctx: TenantContext,
        *,
        run: dm.IngestionRun,
        event: NormalizedConnectorEvent,
        counters: RunCounters,
    ) -> None:
        try:
            signal_type = _EVENT_TO_SIGNAL.get(event.event_type)
            if signal_type is None:
                raise ConnectorError(
                    ConnectorErrorCategory.NORMALIZATION_FAILED,
                    f"Unsupported event type: {event.event_type}",
                    retryable=False,
                )
            from app.domain.enterprise_enums import EnterpriseEntityType

            subject_type = EnterpriseEntityType(event.subject_type)
            subject_id = build_entity_id(
                "subj", ctx.tenant_id, event.subject_type, event.subject_external_id
            )
            signal = dm.EvidenceSignal(
                evidence_signal_id=build_entity_id(
                    "sig",
                    ctx.tenant_id,
                    event.data_source_id,
                    event.source_record_id,
                    signal_type.value,
                    event.payload_hash,
                ),
                tenant_id=ctx.tenant_id,
                data_source_id=event.data_source_id,
                ingestion_run_id=run.ingestion_run_id,
                source_record_id=event.source_record_id,
                signal_type=signal_type,
                subject_type=subject_type,
                subject_id=subject_id[:128],
                event_time=event.event_time,
                observed_at=event.observed_at,
                ingested_at=_utcnow(),
                confidence=event.confidence,
                permission_classification=event.permission_classification,
                payload=event.payload,
                payload_hash=event.payload_hash,
                provenance={
                    "normalized_event_id": event.normalized_event_id,
                    "event_type": event.event_type,
                    "stream_name": event.stream_name,
                    "connector_type": event.connector_type.value,
                    "checkpoint_position": event.checkpoint_position,
                    "provider_metadata": event.provider_metadata,
                },
            )
            record, created = self._uow.evidence_signals.append(ctx, signal)
            if created:
                counters.created += 1
                outcome = IngestionReceiptOutcome.CREATED
                _logger.info(
                    "connector.evidence.created tenant_id=%s evidence_signal_id=%s",
                    ctx.tenant_id,
                    record.evidence_signal_id,
                )
            else:
                counters.deduplicated += 1
                outcome = IngestionReceiptOutcome.DEDUPLICATED
                _logger.info(
                    "connector.evidence.deduplicated tenant_id=%s evidence_signal_id=%s",
                    ctx.tenant_id,
                    record.evidence_signal_id,
                )

            projected = self._projections.apply(
                ctx, event, evidence_signal_id=record.evidence_signal_id
            )
            if projected:
                counters.projected += 1
                if outcome == IngestionReceiptOutcome.CREATED:
                    outcome = IngestionReceiptOutcome.PROJECTED
                _logger.info(
                    "connector.projection.applied tenant_id=%s event_type=%s",
                    ctx.tenant_id,
                    event.event_type,
                )

            receipt = dm.IngestionReceipt(
                ingestion_receipt_id=build_entity_id(
                    "rcpt",
                    ctx.tenant_id,
                    run.ingestion_run_id,
                    event.stream_name,
                    event.source_record_id,
                    event.payload_hash,
                ),
                tenant_id=ctx.tenant_id,
                ingestion_run_id=run.ingestion_run_id,
                data_source_id=event.data_source_id,
                stream_name=event.stream_name,
                source_record_id=event.source_record_id,
                normalized_event_id=event.normalized_event_id,
                evidence_signal_id=record.evidence_signal_id,
                payload_hash=event.payload_hash,
                observed_at=event.observed_at,
                outcome=outcome,
                checkpoint_position=event.checkpoint_position,
            )
            self._uow.ingestion_receipts.append(ctx, receipt)
            self._uow.commit()
            _logger.info(
                "connector.receipt.appended tenant_id=%s outcome=%s source_record_id=%s",
                ctx.tenant_id,
                outcome.value,
                event.source_record_id,
            )
        except Exception as exc:
            self._uow.rollback()
            category = (
                exc.category
                if isinstance(exc, ConnectorError)
                else ConnectorErrorCategory.PERSISTENCE_ERROR
            )
            if (
                isinstance(exc, ConnectorError)
                and exc.category == ConnectorErrorCategory.PROJECTION_ERROR
            ):
                category = ConnectorErrorCategory.PROJECTION_ERROR
            self._dead_letter_event(
                ctx,
                run=run,
                event=event,
                category=category,
                summary=str(exc),
            )
            counters.dead_lettered += 1

    def _dead_letter_event(
        self,
        ctx: TenantContext,
        *,
        run: dm.IngestionRun,
        event: NormalizedConnectorEvent | None,
        category: ConnectorErrorCategory,
        summary: str,
        source_record_id: str | None = None,
        stream_name: str = "unknown",
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        payload = event.payload if event else (raw_payload or {})
        dl = dm.IngestionDeadLetter(
            dead_letter_id=build_entity_id(
                "dl",
                ctx.tenant_id,
                run.ingestion_run_id,
                event.source_record_id if event else (source_record_id or "none"),
                category.value,
                str(uuid.uuid4())[:8],
            ),
            tenant_id=ctx.tenant_id,
            ingestion_run_id=run.ingestion_run_id,
            data_source_id=run.data_source_id,
            stream_name=event.stream_name if event else stream_name,
            source_record_id=event.source_record_id if event else source_record_id,
            normalized_event_id=event.normalized_event_id if event else None,
            event_type=event.event_type if event else None,
            payload_hash=event.payload_hash if event else None,
            redacted_payload=redact_payload(payload),
            error_category=category.value,
            sanitized_error_summary=sanitize_error_message(summary),
            attempt_count=1,
            replay_state=DeadLetterReplayState.PENDING,
        )
        self._uow.ingestion_dead_letters.append(ctx, dl)
        if event is not None:
            receipt = dm.IngestionReceipt(
                ingestion_receipt_id=build_entity_id(
                    "rcpt",
                    ctx.tenant_id,
                    run.ingestion_run_id,
                    event.stream_name,
                    event.source_record_id,
                    event.payload_hash or "dead",
                    "dl",
                ),
                tenant_id=ctx.tenant_id,
                ingestion_run_id=run.ingestion_run_id,
                data_source_id=run.data_source_id,
                stream_name=event.stream_name,
                source_record_id=event.source_record_id,
                normalized_event_id=event.normalized_event_id,
                evidence_signal_id=None,
                payload_hash=event.payload_hash,
                observed_at=event.observed_at,
                outcome=IngestionReceiptOutcome.DEAD_LETTERED,
                checkpoint_position=event.checkpoint_position,
                error_category=category.value,
            )
            self._uow.ingestion_receipts.append(ctx, receipt)
        self._uow.commit()
        _logger.info(
            "connector.event.dead_lettered tenant_id=%s category=%s stream=%s",
            ctx.tenant_id,
            category.value,
            dl.stream_name,
        )

    def _advance_checkpoint(
        self,
        ctx: TenantContext,
        *,
        data_source_id: str,
        stream_name: str,
        cursor: ConnectorCheckpointCursor,
        run_id: str,
        expected_version: int | None,
    ) -> None:
        # Reject credential-like keys in cursor payload.
        for key in cursor.payload:
            lowered = str(key).lower()
            if any(s in lowered for s in ("token", "password", "secret", "authorization")):
                raise ConnectorError(
                    ConnectorErrorCategory.INVALID_CONFIGURATION,
                    "Checkpoint cursor must not contain credential material",
                    retryable=False,
                )
        from app.services.persistence.snapshot_service import canonical_json

        encoded = canonical_json(cursor.payload)
        if len(encoded) > 4096:
            raise ConnectorError(
                ConnectorErrorCategory.PAYLOAD_TOO_LARGE,
                "Checkpoint cursor exceeds size bound",
                retryable=False,
            )
        checkpoint = dm.ConnectorCheckpoint(
            connector_checkpoint_id=build_entity_id(
                "ckpt", ctx.tenant_id, data_source_id, stream_name
            ),
            tenant_id=ctx.tenant_id,
            data_source_id=data_source_id,
            stream_name=stream_name,
            cursor_schema_version=cursor.schema_version,
            cursor_payload=cursor.payload,
            cursor_hash=snapshot_hash(cursor.payload),
            high_watermark_time=cursor.high_watermark_time,
            high_watermark_source_id=cursor.high_watermark_source_id,
            etag=cursor.etag,
            last_successful_run_id=run_id,
            version=1,
        )
        try:
            self._uow.connector_checkpoints.upsert(
                ctx, checkpoint, expected_version=expected_version
            )
            self._uow.commit()
            _logger.info(
                "connector.checkpoint.advanced tenant_id=%s data_source_id=%s stream=%s",
                ctx.tenant_id,
                data_source_id,
                stream_name,
            )
        except Exception:
            _logger.info(
                "connector.checkpoint.conflict tenant_id=%s data_source_id=%s stream=%s",
                ctx.tenant_id,
                data_source_id,
                stream_name,
            )
            self._uow.rollback()
            raise

    def replay_dead_letter(self, ctx: TenantContext, dead_letter_id: str) -> dm.IngestionDeadLetter:
        """Manually replay a safe normalized dead-letter payload (no distributed worker)."""
        dl = self._uow.ingestion_dead_letters.get(ctx, dead_letter_id)
        if dl is None:
            raise EnterpriseNotFoundError("Dead letter not found for this tenant")
        if dl.replay_state == DeadLetterReplayState.REPLAYED:
            return dl
        if not dl.event_type or not dl.redacted_payload or not dl.source_record_id:
            updated = dl.model_copy(
                update={
                    "replay_state": DeadLetterReplayState.FAILED,
                    "attempt_count": dl.attempt_count + 1,
                    "sanitized_error_summary": sanitize_error_message(
                        "Dead letter lacks replayable normalized payload"
                    ),
                }
            )
            result = self._uow.ingestion_dead_letters.update(ctx, updated)
            self._uow.commit()
            return result

        run = self._uow.ingestion_runs.get_run(ctx, dl.ingestion_run_id)
        if run is None:
            raise EnterpriseNotFoundError("Original ingestion run not found")

        try:
            payload = dict(dl.redacted_payload)
            if payload.get("_truncated"):
                raise ConnectorError(
                    ConnectorErrorCategory.PAYLOAD_TOO_LARGE,
                    "Cannot replay truncated dead-letter payload",
                    retryable=False,
                )
            payload_hash = dl.payload_hash or snapshot_hash(payload)
            event = NormalizedConnectorEvent(
                normalized_event_id=dl.normalized_event_id
                or build_entity_id("nev", ctx.tenant_id, dl.dead_letter_id),
                tenant_id=ctx.tenant_id,
                data_source_id=dl.data_source_id,
                connector_type=self._uow.data_sources.get_data_source(
                    ctx, dl.data_source_id
                ).source_type,  # type: ignore[union-attr]
                stream_name=dl.stream_name,
                source_record_id=dl.source_record_id,
                event_type=dl.event_type,
                subject_type=_EVENT_TO_SUBJECT.get(dl.event_type, ("repository",))[0],
                subject_external_id=str(payload.get("external_id") or dl.source_record_id),
                event_time=_utcnow(),
                observed_at=_utcnow(),
                normalized_at=_utcnow(),
                permission_classification=PermissionClassification.INTERNAL,
                payload=payload,
                payload_hash=payload_hash,
            )
            counters = RunCounters()
            self._persist_event(ctx, run=run, event=event, counters=counters)
            if counters.dead_lettered:
                raise ConnectorError(
                    ConnectorErrorCategory.PERSISTENCE_ERROR,
                    "Replay produced another dead letter",
                    retryable=False,
                )
            updated = dl.model_copy(
                update={
                    "replay_state": DeadLetterReplayState.REPLAYED,
                    "attempt_count": dl.attempt_count + 1,
                    "resolved_at": _utcnow(),
                }
            )
            result = self._uow.ingestion_dead_letters.update(ctx, updated)
            self._uow.commit()
            return result
        except Exception as exc:
            self._uow.rollback()
            updated = dl.model_copy(
                update={
                    "replay_state": DeadLetterReplayState.FAILED,
                    "attempt_count": dl.attempt_count + 1,
                    "sanitized_error_summary": sanitize_error_message(str(exc)),
                }
            )
            result = self._uow.ingestion_dead_letters.update(ctx, updated)
            self._uow.commit()
            return result


def _map_ingestion_error(category: ConnectorErrorCategory) -> IngestionErrorCategory:
    mapping = {
        ConnectorErrorCategory.AUTHENTICATION_ERROR: IngestionErrorCategory.AUTHENTICATION,
        ConnectorErrorCategory.MISSING_CREDENTIAL: IngestionErrorCategory.AUTHENTICATION,
        ConnectorErrorCategory.RATE_LIMITED: IngestionErrorCategory.RATE_LIMITED,
        ConnectorErrorCategory.PROVIDER_UNAVAILABLE: IngestionErrorCategory.UPSTREAM_UNAVAILABLE,
        ConnectorErrorCategory.TIMEOUT: IngestionErrorCategory.UPSTREAM_UNAVAILABLE,
        ConnectorErrorCategory.TRANSPORT_ERROR: IngestionErrorCategory.UPSTREAM_UNAVAILABLE,
        ConnectorErrorCategory.INVALID_CONFIGURATION: IngestionErrorCategory.VALIDATION,
        ConnectorErrorCategory.NORMALIZATION_FAILED: IngestionErrorCategory.VALIDATION,
        ConnectorErrorCategory.MALFORMED_RESPONSE: IngestionErrorCategory.VALIDATION,
    }
    return mapping.get(category, IngestionErrorCategory.INTERNAL)
