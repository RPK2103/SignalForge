"""Tenant-scoped repositories for Continuous Scenario Intelligence (Prompt 5)."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.db.models import scenario_intelligence as orm
from app.domain import scenario_models as dm
from app.domain.enterprise_models import Page
from app.domain.scenario_enums import ScenarioRunState, ScenarioWatchLifecycle
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import (
    EnterpriseConflictError,
    EnterpriseNotFoundError,
    EnterpriseValidationError,
)

_MAX_PAGE_SIZE = 100
DTO = TypeVar("DTO", bound=BaseModel)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_dto(dto_cls: type[DTO], row: object) -> DTO:
    return dto_cls.model_validate(row, from_attributes=True)


def _dump(model: BaseModel, ctx: TenantContext) -> dict:
    data = model.model_dump()
    data["tenant_id"] = ctx.tenant_id
    for key, value in list(data.items()):
        if hasattr(value, "value"):
            data[key] = value.value
        elif isinstance(value, list) and value and hasattr(value[0], "value"):
            data[key] = [v.value if hasattr(v, "value") else v for v in value]
    for ts_key in ("created_at", "updated_at"):
        if ts_key in data and data[ts_key] is None:
            data.pop(ts_key)
    return data


def _page(dto_cls: type[DTO], rows: Sequence, total: int, limit: int, offset: int) -> Page:
    normalized_limit = max(1, min(limit, _MAX_PAGE_SIZE))
    return Page[dto_cls](
        items=[_to_dto(dto_cls, row) for row in rows],
        total=total,
        limit=normalized_limit,
        offset=max(0, offset),
    )


class _ScenarioTenantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def _insert_guard(self, conflict_message: str):
        try:
            yield
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise EnterpriseConflictError(conflict_message) from exc

    def _tenant_get(self, model, pk_attr: InstrumentedAttribute, pk: str, ctx: TenantContext):
        return self._session.scalar(
            select(model).where(pk_attr == pk, model.tenant_id == ctx.tenant_id)
        )

    def _paginate(
        self,
        query: Select,
        count_query: Select,
        dto_cls: type[DTO],
        *,
        limit: int,
        offset: int,
    ) -> Page:
        normalized_limit = max(1, min(limit, _MAX_PAGE_SIZE))
        normalized_offset = max(0, offset)
        total = int(self._session.scalar(count_query) or 0)
        rows = self._session.scalars(query.limit(normalized_limit).offset(normalized_offset)).all()
        return _page(dto_cls, rows, total, normalized_limit, normalized_offset)


class ScenarioDefinitionRepository(_ScenarioTenantRepository):
    def get(self, ctx: TenantContext, scenario_definition_id: str) -> dm.ScenarioDefinition | None:
        row = self._tenant_get(
            orm.ScenarioDefinition,
            orm.ScenarioDefinition.scenario_definition_id,
            scenario_definition_id,
            ctx,
        )
        return _to_dto(dm.ScenarioDefinition, row) if row else None

    def require(self, ctx: TenantContext, scenario_definition_id: str) -> dm.ScenarioDefinition:
        item = self.get(ctx, scenario_definition_id)
        if item is None:
            raise EnterpriseNotFoundError("Scenario definition not found for this tenant")
        return item

    def list(
        self,
        ctx: TenantContext,
        *,
        limit: int = 20,
        offset: int = 0,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> Page[dm.ScenarioDefinition]:
        filters = [orm.ScenarioDefinition.tenant_id == ctx.tenant_id]
        if target_type:
            filters.append(orm.ScenarioDefinition.target_type == target_type)
        if target_id:
            filters.append(orm.ScenarioDefinition.target_id == target_id)
        base = select(orm.ScenarioDefinition).where(and_(*filters))
        return self._paginate(
            base.order_by(
                orm.ScenarioDefinition.name.asc(),
                orm.ScenarioDefinition.scenario_definition_id.asc(),
            ),
            select(func.count()).select_from(orm.ScenarioDefinition).where(and_(*filters)),
            dm.ScenarioDefinition,
            limit=limit,
            offset=offset,
        )

    def create(
        self, ctx: TenantContext, definition: dm.ScenarioDefinition
    ) -> dm.ScenarioDefinition:
        payload = _dump(definition, ctx)
        with self._insert_guard("Scenario definition conflict"):
            self._session.add(orm.ScenarioDefinition(**payload))
        return self.require(ctx, definition.scenario_definition_id)

    def set_current_version(
        self, ctx: TenantContext, scenario_definition_id: str, version_number: int
    ) -> dm.ScenarioDefinition:
        row = self._tenant_get(
            orm.ScenarioDefinition,
            orm.ScenarioDefinition.scenario_definition_id,
            scenario_definition_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Scenario definition not found for this tenant")
        row.current_version = version_number
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.ScenarioDefinition, row)


class ScenarioVersionRepository(_ScenarioTenantRepository):
    def get(self, ctx: TenantContext, scenario_version_id: str) -> dm.ScenarioVersion | None:
        row = self._tenant_get(
            orm.ScenarioVersion,
            orm.ScenarioVersion.scenario_version_id,
            scenario_version_id,
            ctx,
        )
        return _to_dto(dm.ScenarioVersion, row) if row else None

    def require(self, ctx: TenantContext, scenario_version_id: str) -> dm.ScenarioVersion:
        item = self.get(ctx, scenario_version_id)
        if item is None:
            raise EnterpriseNotFoundError("Scenario version not found for this tenant")
        return item

    def get_by_spec_hash(
        self, ctx: TenantContext, specification_hash: str
    ) -> dm.ScenarioVersion | None:
        row = self._session.scalar(
            select(orm.ScenarioVersion).where(
                orm.ScenarioVersion.tenant_id == ctx.tenant_id,
                orm.ScenarioVersion.specification_hash == specification_hash,
            )
        )
        return _to_dto(dm.ScenarioVersion, row) if row else None

    def list_for_definition(
        self,
        ctx: TenantContext,
        scenario_definition_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.ScenarioVersion]:
        filters = [
            orm.ScenarioVersion.tenant_id == ctx.tenant_id,
            orm.ScenarioVersion.scenario_definition_id == scenario_definition_id,
        ]
        base = select(orm.ScenarioVersion).where(and_(*filters))
        return self._paginate(
            base.order_by(orm.ScenarioVersion.version_number.desc()),
            select(func.count()).select_from(orm.ScenarioVersion).where(and_(*filters)),
            dm.ScenarioVersion,
            limit=limit,
            offset=offset,
        )

    def get_latest(
        self, ctx: TenantContext, scenario_definition_id: str
    ) -> dm.ScenarioVersion | None:
        row = self._session.scalar(
            select(orm.ScenarioVersion)
            .where(
                orm.ScenarioVersion.tenant_id == ctx.tenant_id,
                orm.ScenarioVersion.scenario_definition_id == scenario_definition_id,
            )
            .order_by(orm.ScenarioVersion.version_number.desc())
            .limit(1)
        )
        return _to_dto(dm.ScenarioVersion, row) if row else None

    def create(self, ctx: TenantContext, version: dm.ScenarioVersion) -> dm.ScenarioVersion:
        payload = _dump(version, ctx)
        with self._insert_guard("Scenario version conflict"):
            self._session.add(orm.ScenarioVersion(**payload))
        return self.require(ctx, version.scenario_version_id)


class ScenarioWatchRepository(_ScenarioTenantRepository):
    def get(self, ctx: TenantContext, scenario_watch_id: str) -> dm.ScenarioWatch | None:
        row = self._tenant_get(
            orm.ScenarioWatch,
            orm.ScenarioWatch.scenario_watch_id,
            scenario_watch_id,
            ctx,
        )
        return _to_dto(dm.ScenarioWatch, row) if row else None

    def require(self, ctx: TenantContext, scenario_watch_id: str) -> dm.ScenarioWatch:
        item = self.get(ctx, scenario_watch_id)
        if item is None:
            raise EnterpriseNotFoundError("Scenario watch not found for this tenant")
        return item

    def list(
        self,
        ctx: TenantContext,
        *,
        limit: int = 20,
        offset: int = 0,
        lifecycle_state: str | None = None,
    ) -> Page[dm.ScenarioWatch]:
        filters = [orm.ScenarioWatch.tenant_id == ctx.tenant_id]
        if lifecycle_state:
            filters.append(orm.ScenarioWatch.lifecycle_state == lifecycle_state)
        base = select(orm.ScenarioWatch).where(and_(*filters))
        return self._paginate(
            base.order_by(
                orm.ScenarioWatch.created_at.asc(),
                orm.ScenarioWatch.scenario_watch_id.asc(),
            ),
            select(func.count()).select_from(orm.ScenarioWatch).where(and_(*filters)),
            dm.ScenarioWatch,
            limit=limit,
            offset=offset,
        )

    def create(self, ctx: TenantContext, watch: dm.ScenarioWatch) -> dm.ScenarioWatch:
        payload = _dump(watch, ctx)
        with self._insert_guard("Scenario watch conflict"):
            self._session.add(orm.ScenarioWatch(**payload))
        return self.require(ctx, watch.scenario_watch_id)

    def list_active_due(
        self, ctx: TenantContext, now: datetime, *, limit: int = 100
    ) -> list[dm.ScenarioWatch]:
        normalized_limit = max(1, min(limit, _MAX_PAGE_SIZE))
        rows = self._session.scalars(
            select(orm.ScenarioWatch)
            .where(
                orm.ScenarioWatch.tenant_id == ctx.tenant_id,
                orm.ScenarioWatch.lifecycle_state == ScenarioWatchLifecycle.ACTIVE.value,
                (
                    orm.ScenarioWatch.next_eligible_at.is_(None)
                    | (orm.ScenarioWatch.next_eligible_at <= now)
                ),
            )
            .order_by(
                orm.ScenarioWatch.next_eligible_at.asc().nullsfirst(),
                orm.ScenarioWatch.scenario_watch_id.asc(),
            )
            .limit(normalized_limit)
        ).all()
        return [_to_dto(dm.ScenarioWatch, row) for row in rows]

    def try_acquire_lock(
        self, ctx: TenantContext, scenario_watch_id: str, expected_lock_version: int
    ) -> dm.ScenarioWatch | None:
        result = self._session.execute(
            update(orm.ScenarioWatch)
            .where(
                orm.ScenarioWatch.tenant_id == ctx.tenant_id,
                orm.ScenarioWatch.scenario_watch_id == scenario_watch_id,
                orm.ScenarioWatch.lock_version == expected_lock_version,
            )
            .values(
                lock_version=expected_lock_version + 1,
                updated_at=_utcnow(),
            )
        )
        if result.rowcount != 1:
            return None
        self._session.flush()
        return self.get(ctx, scenario_watch_id)

    def update_after_success(
        self,
        ctx: TenantContext,
        scenario_watch_id: str,
        *,
        source_fingerprint: str,
        scenario_run_id: str,
        result_hash: str | None,
        evaluated_at: datetime,
        next_eligible_at: datetime,
    ) -> dm.ScenarioWatch:
        row = self._tenant_get(
            orm.ScenarioWatch,
            orm.ScenarioWatch.scenario_watch_id,
            scenario_watch_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Scenario watch not found for this tenant")
        row.last_source_fingerprint = source_fingerprint
        row.last_scenario_run_id = scenario_run_id
        row.last_result_hash = result_hash
        row.last_evaluated_at = evaluated_at
        row.next_eligible_at = next_eligible_at
        row.consecutive_failures = 0
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.ScenarioWatch, row)

    def update_after_skip(
        self,
        ctx: TenantContext,
        scenario_watch_id: str,
        *,
        evaluated_at: datetime,
        next_eligible_at: datetime,
        source_fingerprint: str | None = None,
    ) -> dm.ScenarioWatch:
        row = self._tenant_get(
            orm.ScenarioWatch,
            orm.ScenarioWatch.scenario_watch_id,
            scenario_watch_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Scenario watch not found for this tenant")
        row.last_evaluated_at = evaluated_at
        row.next_eligible_at = next_eligible_at
        if source_fingerprint is not None:
            row.last_source_fingerprint = source_fingerprint
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.ScenarioWatch, row)

    def update_after_failure(
        self, ctx: TenantContext, scenario_watch_id: str, *, evaluated_at: datetime
    ) -> dm.ScenarioWatch:
        """Failure must NOT advance source fingerprint."""
        row = self._tenant_get(
            orm.ScenarioWatch,
            orm.ScenarioWatch.scenario_watch_id,
            scenario_watch_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Scenario watch not found for this tenant")
        row.last_evaluated_at = evaluated_at
        row.consecutive_failures = int(row.consecutive_failures or 0) + 1
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.ScenarioWatch, row)

    def set_lifecycle(
        self, ctx: TenantContext, scenario_watch_id: str, lifecycle_state: ScenarioWatchLifecycle
    ) -> dm.ScenarioWatch:
        row = self._tenant_get(
            orm.ScenarioWatch,
            orm.ScenarioWatch.scenario_watch_id,
            scenario_watch_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Scenario watch not found for this tenant")
        row.lifecycle_state = lifecycle_state.value
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.ScenarioWatch, row)


class ScenarioTriggerEventRepository(_ScenarioTenantRepository):
    def get(
        self, ctx: TenantContext, scenario_trigger_event_id: str
    ) -> dm.ScenarioTriggerEvent | None:
        row = self._tenant_get(
            orm.ScenarioTriggerEvent,
            orm.ScenarioTriggerEvent.scenario_trigger_event_id,
            scenario_trigger_event_id,
            ctx,
        )
        return _to_dto(dm.ScenarioTriggerEvent, row) if row else None

    def create(self, ctx: TenantContext, event: dm.ScenarioTriggerEvent) -> dm.ScenarioTriggerEvent:
        payload = _dump(event, ctx)
        with self._insert_guard("Scenario trigger event conflict"):
            self._session.add(orm.ScenarioTriggerEvent(**payload))
        created = self.get(ctx, event.scenario_trigger_event_id)
        if created is None:
            raise EnterpriseNotFoundError("Scenario trigger event not found for this tenant")
        return created

    def list_for_watch(
        self,
        ctx: TenantContext,
        scenario_watch_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.ScenarioTriggerEvent]:
        filters = [
            orm.ScenarioTriggerEvent.tenant_id == ctx.tenant_id,
            orm.ScenarioTriggerEvent.scenario_watch_id == scenario_watch_id,
        ]
        base = select(orm.ScenarioTriggerEvent).where(and_(*filters))
        return self._paginate(
            base.order_by(
                orm.ScenarioTriggerEvent.detected_at.desc(),
                orm.ScenarioTriggerEvent.scenario_trigger_event_id.asc(),
            ),
            select(func.count()).select_from(orm.ScenarioTriggerEvent).where(and_(*filters)),
            dm.ScenarioTriggerEvent,
            limit=limit,
            offset=offset,
        )


class ScenarioRunRepository(_ScenarioTenantRepository):
    def get(self, ctx: TenantContext, scenario_run_id: str) -> dm.ScenarioRun | None:
        row = self._tenant_get(
            orm.ScenarioRun,
            orm.ScenarioRun.scenario_run_id,
            scenario_run_id,
            ctx,
        )
        return _to_dto(dm.ScenarioRun, row) if row else None

    def require(self, ctx: TenantContext, scenario_run_id: str) -> dm.ScenarioRun:
        item = self.get(ctx, scenario_run_id)
        if item is None:
            raise EnterpriseNotFoundError("Scenario run not found for this tenant")
        return item

    def get_by_input_hash(self, ctx: TenantContext, run_input_hash: str) -> dm.ScenarioRun | None:
        row = self._session.scalar(
            select(orm.ScenarioRun).where(
                orm.ScenarioRun.tenant_id == ctx.tenant_id,
                orm.ScenarioRun.run_input_hash == run_input_hash,
            )
        )
        return _to_dto(dm.ScenarioRun, row) if row else None

    def list_for_definition(
        self,
        ctx: TenantContext,
        scenario_definition_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.ScenarioRun]:
        filters = [
            orm.ScenarioRun.tenant_id == ctx.tenant_id,
            orm.ScenarioRun.scenario_definition_id == scenario_definition_id,
        ]
        base = select(orm.ScenarioRun).where(and_(*filters))
        return self._paginate(
            base.order_by(
                orm.ScenarioRun.created_at.desc(),
                orm.ScenarioRun.scenario_run_id.asc(),
            ),
            select(func.count()).select_from(orm.ScenarioRun).where(and_(*filters)),
            dm.ScenarioRun,
            limit=limit,
            offset=offset,
        )

    def list_for_target(
        self,
        ctx: TenantContext,
        target_type: str,
        target_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.ScenarioRun]:
        filters = [
            orm.ScenarioRun.tenant_id == ctx.tenant_id,
            orm.ScenarioRun.target_type == target_type,
            orm.ScenarioRun.target_id == target_id,
        ]
        base = select(orm.ScenarioRun).where(and_(*filters))
        return self._paginate(
            base.order_by(
                orm.ScenarioRun.created_at.desc(),
                orm.ScenarioRun.scenario_run_id.asc(),
            ),
            select(func.count()).select_from(orm.ScenarioRun).where(and_(*filters)),
            dm.ScenarioRun,
            limit=limit,
            offset=offset,
        )

    def create(self, ctx: TenantContext, run: dm.ScenarioRun) -> dm.ScenarioRun:
        payload = _dump(run, ctx)
        with self._insert_guard("Scenario run conflict"):
            self._session.add(orm.ScenarioRun(**payload))
        return self.require(ctx, run.scenario_run_id)

    def update_state(
        self,
        ctx: TenantContext,
        scenario_run_id: str,
        state: ScenarioRunState,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        nodes_examined: int | None = None,
        edges_examined: int | None = None,
        impacts_created: int | None = None,
        result_hash: str | None = None,
        sanitized_error_summary: str | None = None,
    ) -> dm.ScenarioRun:
        row = self._tenant_get(
            orm.ScenarioRun,
            orm.ScenarioRun.scenario_run_id,
            scenario_run_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Scenario run not found for this tenant")
        row.state = state.value
        if started_at is not None:
            row.started_at = started_at
        if completed_at is not None:
            row.completed_at = completed_at
        if nodes_examined is not None:
            row.nodes_examined = nodes_examined
        if edges_examined is not None:
            row.edges_examined = edges_examined
        if impacts_created is not None:
            row.impacts_created = impacts_created
        if result_hash is not None:
            row.result_hash = result_hash
        if sanitized_error_summary is not None:
            row.sanitized_error_summary = sanitized_error_summary[:512]
        self._session.flush()
        return _to_dto(dm.ScenarioRun, row)


class ScenarioFeatureOverlayRepository(_ScenarioTenantRepository):
    def get(
        self, ctx: TenantContext, scenario_feature_overlay_id: str
    ) -> dm.ScenarioFeatureOverlay | None:
        row = self._tenant_get(
            orm.ScenarioFeatureOverlay,
            orm.ScenarioFeatureOverlay.scenario_feature_overlay_id,
            scenario_feature_overlay_id,
            ctx,
        )
        return _to_dto(dm.ScenarioFeatureOverlay, row) if row else None

    def get_by_run(
        self, ctx: TenantContext, scenario_run_id: str
    ) -> dm.ScenarioFeatureOverlay | None:
        row = self._session.scalar(
            select(orm.ScenarioFeatureOverlay).where(
                orm.ScenarioFeatureOverlay.tenant_id == ctx.tenant_id,
                orm.ScenarioFeatureOverlay.scenario_run_id == scenario_run_id,
            )
        )
        return _to_dto(dm.ScenarioFeatureOverlay, row) if row else None

    def create(
        self, ctx: TenantContext, overlay: dm.ScenarioFeatureOverlay
    ) -> dm.ScenarioFeatureOverlay:
        if overlay.training_eligible:
            raise EnterpriseValidationError("scenario overlays must be training_eligible=false")
        payload = _dump(overlay, ctx)
        payload["training_eligible"] = False
        with self._insert_guard("Scenario feature overlay conflict"):
            self._session.add(orm.ScenarioFeatureOverlay(**payload))
        created = self.get(ctx, overlay.scenario_feature_overlay_id)
        if created is None:
            raise EnterpriseNotFoundError("Scenario feature overlay not found for this tenant")
        return created

    def count(self, ctx: TenantContext) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(orm.ScenarioFeatureOverlay)
                .where(orm.ScenarioFeatureOverlay.tenant_id == ctx.tenant_id)
            )
            or 0
        )

    def count_training_eligible(self, ctx: TenantContext) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(orm.ScenarioFeatureOverlay)
                .where(
                    orm.ScenarioFeatureOverlay.tenant_id == ctx.tenant_id,
                    orm.ScenarioFeatureOverlay.training_eligible.is_(True),
                )
            )
            or 0
        )


class ScenarioResultRepository(_ScenarioTenantRepository):
    def get(self, ctx: TenantContext, scenario_result_id: str) -> dm.ScenarioResult | None:
        row = self._tenant_get(
            orm.ScenarioResult,
            orm.ScenarioResult.scenario_result_id,
            scenario_result_id,
            ctx,
        )
        return _to_dto(dm.ScenarioResult, row) if row else None

    def get_by_run(self, ctx: TenantContext, scenario_run_id: str) -> dm.ScenarioResult | None:
        row = self._session.scalar(
            select(orm.ScenarioResult).where(
                orm.ScenarioResult.tenant_id == ctx.tenant_id,
                orm.ScenarioResult.scenario_run_id == scenario_run_id,
            )
        )
        return _to_dto(dm.ScenarioResult, row) if row else None

    def get_by_result_hash(self, ctx: TenantContext, result_hash: str) -> dm.ScenarioResult | None:
        row = self._session.scalar(
            select(orm.ScenarioResult).where(
                orm.ScenarioResult.tenant_id == ctx.tenant_id,
                orm.ScenarioResult.result_hash == result_hash,
            )
        )
        return _to_dto(dm.ScenarioResult, row) if row else None

    def create(self, ctx: TenantContext, result: dm.ScenarioResult) -> dm.ScenarioResult:
        payload = _dump(result, ctx)
        with self._insert_guard("Scenario result conflict"):
            self._session.add(orm.ScenarioResult(**payload))
        created = self.get_by_run(ctx, result.scenario_run_id)
        if created is None:
            raise EnterpriseNotFoundError("Scenario result not found for this tenant")
        return created


class ScenarioImpactRepository(_ScenarioTenantRepository):
    def list_for_run(
        self,
        ctx: TenantContext,
        scenario_run_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[dm.ScenarioImpact]:
        filters = [
            orm.ScenarioImpact.tenant_id == ctx.tenant_id,
            orm.ScenarioImpact.scenario_run_id == scenario_run_id,
        ]
        base = select(orm.ScenarioImpact).where(and_(*filters))
        return self._paginate(
            base.order_by(
                orm.ScenarioImpact.impact_type.asc(),
                orm.ScenarioImpact.scenario_impact_id.asc(),
            ),
            select(func.count()).select_from(orm.ScenarioImpact).where(and_(*filters)),
            dm.ScenarioImpact,
            limit=limit,
            offset=offset,
        )

    def create_many(
        self, ctx: TenantContext, impacts: list[dm.ScenarioImpact]
    ) -> list[dm.ScenarioImpact]:
        created: list[dm.ScenarioImpact] = []
        for impact in impacts:
            payload = _dump(impact, ctx)
            with self._insert_guard("Scenario impact conflict"):
                self._session.add(orm.ScenarioImpact(**payload))
            created.append(impact)
        return created
