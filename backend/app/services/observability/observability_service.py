"""Observability read/manage application service (Phase 3 Prompt 8).

All operations are authorized at the SERVICE layer (deny-by-default), not only at
the route. Reads require ``observability.read``; state changes (SLO definition,
alert acknowledge/resolve, SLO evaluation persistence) require
``observability.manage`` and emit a security audit event.

No raw prompts, evidence, tokens or high-cardinality identifiers are returned.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.unit_of_work import UnitOfWork
from app.domain.observability_models import (
    AlertEventRecord,
    MetricRollupRecord,
    PredictionQualitySnapshotRecord,
    SloDefinitionRecord,
    SloEvaluationRecord,
    SloStatus,
)
from app.observability.alerts import alert_fingerprint, severity_for_slo_status
from app.observability.metrics_reader import MetricsReader
from app.observability.runtime import get_observability_provider
from app.observability.slo import (
    default_slo_definitions,
    evaluate_slo,
    slo_canonical_hash,
)
from app.security.audit import SecurityAuditService
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.enums import Permission, SecurityAuditAction
from app.security.exceptions import SecurityError
from app.security.redaction import hash_identifier

# Indicator -> reader method mapping used by SLO evaluation.
_INDICATOR_READERS = {
    "api_5xx_free_ratio": "api_5xx_free_ratio",
    "api_latency_p95_ms": "api_latency_p95",
    "connector_success_ratio": "connector_success_ratio",
    "required_audit_write_success_ratio": "required_audit_write_success_ratio",
    "ai_schema_valid_ratio": "ai_schema_valid_ratio",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ObservabilityService:
    def __init__(self, uow: UnitOfWork, authz: AuthorizationService | None = None) -> None:
        self._uow = uow
        self._authz = authz or AuthorizationService()
        self._audit = SecurityAuditService(uow)

    # -- reads -------------------------------------------------------------
    def get_summary(self, context: SecurityContext) -> dict:
        self._authz.require_context(context, Permission.OBSERVABILITY_READ)
        reader = MetricsReader(get_observability_provider())
        p50 = reader.http_latency_percentile(50)
        p95 = reader.http_latency_percentile(95)
        total = reader.http_request_total()
        errors = reader.http_server_errors()
        slo_defs = self._uow.slo_definitions.list_latest(context.tenant_id)
        slo_states: list[dict] = []
        for definition in slo_defs:
            latest = self._uow.slo_evaluations.list(
                context.tenant_id, slo_key=definition.slo_key, limit=1
            )
            slo_states.append(
                {
                    "slo_key": definition.slo_key,
                    "indicator": definition.indicator,
                    "status": latest[0].status if latest else SloStatus.INSUFFICIENT_DATA.value,
                    "observed_value": latest[0].observed_value if latest else None,
                    "objective": definition.objective,
                }
            )
        open_alerts = self._uow.alert_events.list(context.tenant_id, state="open", limit=100)
        runs = self._uow.ai_evaluation_runs.list(context.tenant_id, limit=1)
        pq = self._uow.prediction_quality_snapshots.list(context.tenant_id, limit=1)
        return {
            "telemetry_available": reader.available,
            "http": {
                "request_total": total,
                "server_error_total": errors,
                "server_error_rate": (errors / total) if total else None,
                "authentication_denials": reader.http_authentication_denials(),
                "authorization_denials": reader.http_authorization_denials(),
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
            },
            "ai": {
                "fallback_rate": reader.fallback_rate().value,
                "grounding_failure_rate": reader.grounding_failure_rate().value,
                "schema_valid_ratio": reader.ai_schema_valid_ratio().value,
            },
            "connectors": {"success_ratio": reader.connector_success_ratio().value},
            "slo_states": slo_states,
            "open_alert_count": len(open_alerts),
            "latest_ai_run": runs[0].model_dump(mode="json") if runs else None,
            "prediction_quality_available": bool(pq),
        }

    def list_metrics(
        self, context: SecurityContext, *, metric_name: str | None = None, limit: int = 50
    ) -> list[MetricRollupRecord]:
        self._authz.require_context(context, Permission.OBSERVABILITY_READ)
        return self._uow.metric_rollups.list(
            context.tenant_id, metric_name=metric_name, limit=limit
        )

    def get_freshness(self, context: SecurityContext) -> list[dict]:
        self._authz.require_context(context, Permission.OBSERVABILITY_READ)
        rows = self._uow.metric_rollups.list(
            context.tenant_id,
            metric_name="connector.evidence.freshness_age_seconds",
            limit=50,
        )
        return [
            {
                "source_type": r.dimensions.get("source_type", "unknown"),
                "freshness_state": r.dimensions.get("freshness_state", "unavailable"),
                "age_seconds": r.value,
                "window_end": r.window_end.isoformat(),
            }
            for r in rows
        ]

    def list_slo_definitions(self, context: SecurityContext) -> list[SloDefinitionRecord]:
        self._authz.require_context(context, Permission.OBSERVABILITY_READ)
        return self._uow.slo_definitions.list_latest(context.tenant_id)

    def list_slo_evaluations(
        self, context: SecurityContext, *, slo_key: str | None = None, limit: int = 50
    ) -> list[SloEvaluationRecord]:
        self._authz.require_context(context, Permission.OBSERVABILITY_READ)
        return self._uow.slo_evaluations.list(context.tenant_id, slo_key=slo_key, limit=limit)

    def list_alerts(
        self, context: SecurityContext, *, state: str | None = None, limit: int = 50
    ) -> list[AlertEventRecord]:
        self._authz.require_context(context, Permission.OBSERVABILITY_READ)
        return self._uow.alert_events.list(context.tenant_id, state=state, limit=limit)

    def list_prediction_quality(
        self, context: SecurityContext, *, model_version: str | None = None, limit: int = 50
    ) -> list[PredictionQualitySnapshotRecord]:
        self._authz.require_context(context, Permission.OBSERVABILITY_READ)
        return self._uow.prediction_quality_snapshots.list(
            context.tenant_id, model_version=model_version, limit=limit
        )

    # -- management --------------------------------------------------------
    def ensure_default_slo_definitions(self, context: SecurityContext) -> list[SloDefinitionRecord]:
        self._authz.require_context(context, Permission.OBSERVABILITY_MANAGE)
        created: list[SloDefinitionRecord] = []
        for spec in default_slo_definitions():
            existing = self._uow.slo_definitions.get_latest(context.tenant_id, spec.slo_key)
            if existing is not None:
                created.append(existing)
                continue
            record = self._uow.slo_definitions.create(
                context.tenant_id,
                slo_key=spec.slo_key,
                indicator=spec.indicator,
                objective=spec.objective,
                comparison=spec.comparison,
                unit=spec.unit,
                window_seconds=spec.window_seconds,
                min_sample_count=spec.min_sample_count,
                description=spec.description,
            )
            self._audit.record_sensitive_action(
                context,
                action=SecurityAuditAction.SLO_DEFINITION_CHANGED,
                permission=Permission.OBSERVABILITY_MANAGE,
                resource_type="slo_definition",
                resource_id=record.id,
                metadata={"slo_key": spec.slo_key, "version": record.version},
            )
            created.append(record)
        self._uow.commit()
        return created

    def evaluate_slos(self, context: SecurityContext) -> list[SloEvaluationRecord]:
        """Deterministically evaluate all SLOs and open/resolve correlated alerts."""
        self._authz.require_context(context, Permission.OBSERVABILITY_MANAGE)
        definitions = self._uow.slo_definitions.list_latest(context.tenant_id)
        if not definitions:
            definitions = self.ensure_default_slo_definitions(context)
        reader = MetricsReader(get_observability_provider())
        now = _utcnow()
        results: list[SloEvaluationRecord] = []
        for definition in definitions:
            window_start = now - timedelta(seconds=definition.window_seconds)
            reader_name = _INDICATOR_READERS.get(definition.indicator)
            if reader_name is None:
                observed, sample_count = None, 0
            else:
                indicator = getattr(reader, reader_name)()
                observed, sample_count = indicator.value, indicator.sample_count
            computation = evaluate_slo(
                observed_value=observed,
                sample_count=sample_count,
                objective=definition.objective,
                comparison=definition.comparison,
                min_sample_count=definition.min_sample_count,
            )
            canonical = slo_canonical_hash(
                slo_key=definition.slo_key,
                slo_version=definition.version,
                window_start=window_start.isoformat(),
                window_end=now.isoformat(),
                observed=observed,
            )
            record = self._uow.slo_evaluations.append(
                context.tenant_id,
                slo_key=definition.slo_key,
                slo_version=definition.version,
                indicator=definition.indicator,
                window_start=window_start,
                window_end=now,
                evaluation_cutoff=now,
                observed_value=observed,
                objective=definition.objective,
                sample_count=sample_count,
                status=computation.status.value,
                canonical_hash=canonical,
            )
            self._sync_alert_for_slo(context, definition, computation.status, record.id)
            results.append(record)
        self._uow.commit()
        return results

    def acknowledge_alert(self, context: SecurityContext, *, alert_id: str) -> AlertEventRecord:
        self._authz.require_context(context, Permission.OBSERVABILITY_MANAGE)
        row = self._uow.alert_events.get(context.tenant_id, alert_id)
        if row is None:
            # Foreign/nonexistent alerts are indistinguishable.
            raise SecurityError("Alert not found")
        record = self._uow.alert_events.transition(
            row,
            new_state="acknowledged",
            actor_hash=hash_identifier(context.principal_id),
            reason="operator_acknowledged",
        )
        self._audit.record_sensitive_action(
            context,
            action=SecurityAuditAction.ALERT_ACKNOWLEDGED,
            permission=Permission.OBSERVABILITY_MANAGE,
            resource_type="alert_event",
            resource_id=alert_id,
            metadata={"fingerprint": record.fingerprint},
        )
        self._uow.commit()
        return record

    def resolve_alert(self, context: SecurityContext, *, alert_id: str) -> AlertEventRecord:
        self._authz.require_context(context, Permission.OBSERVABILITY_MANAGE)
        row = self._uow.alert_events.get(context.tenant_id, alert_id)
        if row is None:
            raise SecurityError("Alert not found")
        record = self._uow.alert_events.transition(
            row,
            new_state="resolved",
            actor_hash=hash_identifier(context.principal_id),
            reason="operator_resolved",
        )
        self._audit.record_sensitive_action(
            context,
            action=SecurityAuditAction.ALERT_RESOLVED,
            permission=Permission.OBSERVABILITY_MANAGE,
            resource_type="alert_event",
            resource_id=alert_id,
            metadata={"fingerprint": record.fingerprint},
        )
        self._uow.commit()
        return record

    # -- internal ----------------------------------------------------------
    def _sync_alert_for_slo(
        self,
        context: SecurityContext,
        definition: SloDefinitionRecord,
        status: SloStatus,
        evaluation_id: str,
    ) -> None:
        severity = severity_for_slo_status(status)
        fingerprint = alert_fingerprint(
            source="slo",
            reason_code=f"slo_{status.value}",
            subject=definition.slo_key,
        )
        if severity is None:
            # Healthy/insufficient -> resolve any open alert for this SLO condition.
            existing = self._uow.alert_events.get_by_fingerprint(context.tenant_id, fingerprint)
            if existing is not None and existing.state != "resolved":
                self._uow.alert_events.transition(
                    existing, new_state="resolved", reason="slo_recovered"
                )
            return
        self._uow.alert_events.upsert_open(
            context.tenant_id,
            fingerprint=fingerprint,
            severity=severity.value,
            source="slo",
            title=f"SLO {definition.slo_key} {status.value}",
            reason_code=f"slo_{status.value}",
            correlated_slo_key=definition.slo_key,
            correlated_run_id=evaluation_id,
            metadata={"indicator": definition.indicator},
        )
