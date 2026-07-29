"""Watch-based continuous scenario re-evaluation (no queues/workers)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.scenario_constants import (
    DEFAULT_HORIZON_DAYS,
    MAX_WATCHES_PER_EVALUATION_BATCH,
    MIN_WATCH_INTERVAL_MINUTES,
)
from app.domain.scenario_enums import (
    ScenarioRunMode,
    ScenarioTriggerAction,
    ScenarioTriggerReason,
    ScenarioWatchLifecycle,
    ScenarioWatchMode,
)
from app.domain.scenario_models import (
    ScenarioDueEvaluationSummary,
    ScenarioTriggerEvent,
    ScenarioWatch,
    ScenarioWatchEvaluationResult,
)
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import (
    EnterpriseValidationError,
)
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.scenarios.execution import ScenarioExecutionService
from app.services.scenarios.fingerprints import (
    compute_source_fingerprint,
    diff_fingerprint_components,
)

logger = logging.getLogger("signalforge.scenarios")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ScenarioWatchService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._execution = ScenarioExecutionService(uow)

    def create_watch(
        self,
        ctx: TenantContext,
        *,
        scenario_version_id: str,
        watch_mode: ScenarioWatchMode = ScenarioWatchMode.ON_CHANGE,
        minimum_interval_minutes: int = MIN_WATCH_INTERVAL_MINUTES,
    ) -> ScenarioWatch:
        if minimum_interval_minutes < MIN_WATCH_INTERVAL_MINUTES:
            raise EnterpriseValidationError(
                f"minimum_interval_minutes must be >= {MIN_WATCH_INTERVAL_MINUTES}"
            )
        version = self._uow.scenario_versions.require(ctx, scenario_version_id)
        definition = self._uow.scenario_definitions.require(ctx, version.scenario_definition_id)
        watch_id = build_entity_id(
            "swatch",
            ctx.tenant_id,
            version.scenario_version_id,
            definition.target_type.value
            if hasattr(definition.target_type, "value")
            else str(definition.target_type),
            definition.target_id,
        )
        watch = ScenarioWatch(
            tenant_id=ctx.tenant_id,
            scenario_watch_id=watch_id,
            scenario_definition_id=definition.scenario_definition_id,
            scenario_version_id=version.scenario_version_id,
            target_type=definition.target_type,
            target_id=definition.target_id,
            watch_mode=watch_mode,
            lifecycle_state=ScenarioWatchLifecycle.ACTIVE,
            minimum_interval_minutes=minimum_interval_minutes,
            next_eligible_at=_utcnow(),
        )
        created = self._uow.scenario_watches.create(ctx, watch)
        logger.info(
            "scenario.watch.created tenant_id=%s watch_id=%s",
            ctx.tenant_id,
            created.scenario_watch_id,
        )
        return created

    def pause(self, ctx: TenantContext, watch_id: str) -> ScenarioWatch:
        return self._uow.scenario_watches.set_lifecycle(
            ctx, watch_id, ScenarioWatchLifecycle.PAUSED
        )

    def resume(self, ctx: TenantContext, watch_id: str) -> ScenarioWatch:
        return self._uow.scenario_watches.set_lifecycle(
            ctx, watch_id, ScenarioWatchLifecycle.ACTIVE
        )

    def disable(self, ctx: TenantContext, watch_id: str) -> ScenarioWatch:
        return self._uow.scenario_watches.set_lifecycle(
            ctx, watch_id, ScenarioWatchLifecycle.DISABLED
        )

    def evaluate_watch(
        self,
        ctx: TenantContext,
        watch_id: str,
        *,
        as_of_at: datetime | None = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        force: bool = False,
    ) -> ScenarioWatchEvaluationResult:
        watch = self._uow.scenario_watches.require(ctx, watch_id)
        if watch.lifecycle_state != ScenarioWatchLifecycle.ACTIVE and not force:
            raise EnterpriseValidationError("Watch is not active")

        now = _utcnow()
        locked = self._uow.scenario_watches.try_acquire_lock(
            ctx, watch.scenario_watch_id, watch.lock_version
        )
        if locked is None:
            logger.info(
                "scenario.watch.concurrent_evaluation_rejected tenant_id=%s watch_id=%s",
                ctx.tenant_id,
                watch_id,
            )
            trigger = self._persist_trigger(
                ctx,
                watch=watch,
                reason=ScenarioTriggerReason.NO_RELEVANT_CHANGE,
                action=ScenarioTriggerAction.SKIPPED_NO_CHANGE,
                previous=watch.last_source_fingerprint,
                current=watch.last_source_fingerprint,
                changed=[],
                error="concurrent_evaluation_rejected",
            )
            return ScenarioWatchEvaluationResult(
                watch=watch,
                trigger=trigger,
                action=ScenarioTriggerAction.SKIPPED_NO_CHANGE,
            )

        watch = locked
        next_eligible = _aware(watch.next_eligible_at)
        if not force and next_eligible is not None and next_eligible > now:
            trigger = self._persist_trigger(
                ctx,
                watch=watch,
                reason=ScenarioTriggerReason.MINIMUM_INTERVAL_NOT_ELAPSED,
                action=ScenarioTriggerAction.SKIPPED_INTERVAL,
                previous=watch.last_source_fingerprint,
                current=watch.last_source_fingerprint,
                changed=[],
            )
            logger.info(
                "scenario.watch.skipped_interval tenant_id=%s watch_id=%s",
                ctx.tenant_id,
                watch_id,
            )
            return ScenarioWatchEvaluationResult(
                watch=watch,
                trigger=trigger,
                action=ScenarioTriggerAction.SKIPPED_INTERVAL,
            )

        version = self._uow.scenario_versions.require(ctx, watch.scenario_version_id)
        as_of = as_of_at or now
        parts = compute_source_fingerprint(
            self._uow,
            ctx,
            target_type=watch.target_type,
            target_id=watch.target_id,
            as_of_at=as_of,
            horizon_days=horizon_days,
            scenario_version_hash=version.specification_hash,
        )

        previous_components = None
        if watch.last_source_fingerprint and watch.last_source_fingerprint == parts.fingerprint:
            changed, reason = [], ScenarioTriggerReason.NO_RELEVANT_CHANGE
        else:
            # We only store the aggregate fingerprint on the watch; component-level
            # diff uses current components vs empty previous when fingerprint changed.
            previous_components = {} if watch.last_source_fingerprint else None
            changed, reason = diff_fingerprint_components(previous_components, parts.components)
            if watch.last_source_fingerprint is None:
                reason = ScenarioTriggerReason.MANUAL_REQUEST
            elif not changed:
                # Fingerprint object differs but component map matched — treat as change.
                changed = ["source_fingerprint"]
                reason = ScenarioTriggerReason.TARGET_CHANGED

        next_eligible = now + timedelta(minutes=watch.minimum_interval_minutes)

        if watch.last_source_fingerprint == parts.fingerprint and not force:
            trigger = self._persist_trigger(
                ctx,
                watch=watch,
                reason=ScenarioTriggerReason.NO_RELEVANT_CHANGE,
                action=ScenarioTriggerAction.SKIPPED_NO_CHANGE,
                previous=watch.last_source_fingerprint,
                current=parts.fingerprint,
                changed=[],
            )
            updated = self._uow.scenario_watches.update_after_skip(
                ctx,
                watch.scenario_watch_id,
                evaluated_at=now,
                next_eligible_at=next_eligible,
                source_fingerprint=parts.fingerprint,
            )
            logger.info(
                "scenario.watch.skipped_no_change tenant_id=%s watch_id=%s",
                ctx.tenant_id,
                watch_id,
            )
            return ScenarioWatchEvaluationResult(
                watch=updated,
                trigger=trigger,
                action=ScenarioTriggerAction.SKIPPED_NO_CHANGE,
            )

        try:
            bundle = self._execution.execute(
                ctx,
                scenario_version_id=watch.scenario_version_id,
                as_of_at=as_of,
                horizon_days=horizon_days,
                run_mode=ScenarioRunMode.WATCH,
            )
            trigger = self._persist_trigger(
                ctx,
                watch=watch,
                reason=reason if changed else ScenarioTriggerReason.MANUAL_REQUEST,
                action=ScenarioTriggerAction.EVALUATED,
                previous=watch.last_source_fingerprint,
                current=parts.fingerprint,
                changed=changed or ["manual_request"],
                run_id=bundle.run.scenario_run_id,
            )
            updated = self._uow.scenario_watches.update_after_success(
                ctx,
                watch.scenario_watch_id,
                source_fingerprint=parts.fingerprint,
                scenario_run_id=bundle.run.scenario_run_id,
                result_hash=bundle.result.result_hash if bundle.result else None,
                evaluated_at=now,
                next_eligible_at=next_eligible,
            )
            logger.info(
                "scenario.watch.evaluated tenant_id=%s watch_id=%s run_id=%s",
                ctx.tenant_id,
                watch_id,
                bundle.run.scenario_run_id,
            )
            return ScenarioWatchEvaluationResult(
                watch=updated,
                trigger=trigger,
                run=bundle.run,
                result=bundle.result,
                action=ScenarioTriggerAction.EVALUATED,
            )
        except Exception as exc:
            # Do NOT advance fingerprint on failure.
            trigger = self._persist_trigger(
                ctx,
                watch=watch,
                reason=reason if changed else ScenarioTriggerReason.MANUAL_REQUEST,
                action=ScenarioTriggerAction.FAILED,
                previous=watch.last_source_fingerprint,
                current=parts.fingerprint,
                changed=changed,
                error=str(exc)[:512],
            )
            updated = self._uow.scenario_watches.update_after_failure(
                ctx, watch.scenario_watch_id, evaluated_at=now
            )
            logger.info(
                "scenario.watch.failed tenant_id=%s watch_id=%s",
                ctx.tenant_id,
                watch_id,
            )
            return ScenarioWatchEvaluationResult(
                watch=updated,
                trigger=trigger,
                action=ScenarioTriggerAction.FAILED,
            )

    def evaluate_due(
        self,
        ctx: TenantContext,
        *,
        limit: int = MAX_WATCHES_PER_EVALUATION_BATCH,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> ScenarioDueEvaluationSummary:
        now = _utcnow()
        due = self._uow.scenario_watches.list_active_due(
            ctx, now, limit=min(limit, MAX_WATCHES_PER_EVALUATION_BATCH)
        )
        summary = ScenarioDueEvaluationSummary()
        for watch in due:
            result = self.evaluate_watch(
                ctx,
                watch.scenario_watch_id,
                horizon_days=horizon_days,
            )
            summary.results.append(result)
            if result.action == ScenarioTriggerAction.EVALUATED:
                summary.evaluated += 1
            elif result.action == ScenarioTriggerAction.SKIPPED_NO_CHANGE:
                summary.skipped_no_change += 1
            elif result.action == ScenarioTriggerAction.SKIPPED_INTERVAL:
                summary.skipped_interval += 1
            else:
                summary.failed += 1
        return summary

    def _persist_trigger(
        self,
        ctx: TenantContext,
        *,
        watch: ScenarioWatch,
        reason: ScenarioTriggerReason,
        action: ScenarioTriggerAction,
        previous: str | None,
        current: str | None,
        changed: list[str],
        run_id: str | None = None,
        error: str | None = None,
    ) -> ScenarioTriggerEvent:
        detected = _utcnow()
        event_id = build_entity_id(
            "strig",
            ctx.tenant_id,
            watch.scenario_watch_id,
            detected.isoformat(),
            action.value,
            snapshot_hash({"changed": changed, "current": current})[:12],
        )
        event = ScenarioTriggerEvent(
            tenant_id=ctx.tenant_id,
            scenario_trigger_event_id=event_id,
            scenario_watch_id=watch.scenario_watch_id,
            detected_at=detected,
            trigger_reason=reason,
            previous_fingerprint=previous,
            current_fingerprint=current,
            changed_components=sorted(set(changed))[:32],
            action=action,
            scenario_run_id=run_id,
            sanitized_error_summary=error,
        )
        created = self._uow.scenario_trigger_events.create(ctx, event)
        logger.info(
            "scenario.trigger.persisted tenant_id=%s watch_id=%s action=%s reason=%s",
            ctx.tenant_id,
            watch.scenario_watch_id,
            action.value,
            reason.value,
        )
        return created
