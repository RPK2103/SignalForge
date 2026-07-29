"""Tenant-scoped repositories for Delivery Prediction (Phase 3 Prompt 4)."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.db.models import prediction as orm
from app.domain import prediction_models as dm
from app.domain.enterprise_models import Page
from app.domain.prediction_enums import (
    ModelState,
    ModelUsageScope,
    OutcomeCategory,
    VerificationStatus,
)
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import (
    CrossTenantAccessError,
    EnterpriseConflictError,
    EnterpriseNotFoundError,
)

_MAX_PAGE_SIZE = 100
_MAX_HORIZON_LIST = 500
DTO = TypeVar("DTO", bound=BaseModel)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


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


def _enum_value(value: object) -> object:
    return value.value if hasattr(value, "value") else value


class _PredictionTenantRepository:
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
        *,
        limit: int,
        offset: int,
    ) -> tuple[Sequence, int]:
        limit = max(1, min(limit, _MAX_PAGE_SIZE))
        offset = max(0, offset)
        total = self._session.scalar(count_query) or 0
        rows = self._session.scalars(query.offset(offset).limit(limit)).all()
        return rows, total

    def _supports_for_update(self) -> bool:
        bind = self._session.get_bind()
        if bind is None:
            return False
        # SQLite accepts FOR UPDATE syntax in some versions but does not lock;
        # skip so application-level unique-active enforcement remains the path.
        return bind.dialect.name not in {"sqlite"}


class DeliveryOutcomeRepository(_PredictionTenantRepository):
    def insert(self, ctx: TenantContext, outcome: dm.DeliveryOutcome) -> dm.DeliveryOutcome:
        with self._insert_guard("Delivery outcome already exists for this tenant"):
            self._session.add(orm.DeliveryOutcome(**_dump(outcome, ctx)))
        return outcome

    def get(self, ctx: TenantContext, delivery_outcome_id: str) -> dm.DeliveryOutcome | None:
        row = self._tenant_get(
            orm.DeliveryOutcome,
            orm.DeliveryOutcome.delivery_outcome_id,
            delivery_outcome_id,
            ctx,
        )
        return _to_dto(dm.DeliveryOutcome, row) if row else None

    def list_labeled(
        self,
        ctx: TenantContext,
        *,
        horizon_days: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[dm.DeliveryOutcome]:
        """Verified + binary_label in {0,1} + finalized outcomes."""
        clause = and_(
            orm.DeliveryOutcome.tenant_id == ctx.tenant_id,
            orm.DeliveryOutcome.verification_status == VerificationStatus.VERIFIED.value,
            orm.DeliveryOutcome.binary_label.in_((0, 1)),
            orm.DeliveryOutcome.finalized_at.is_not(None),
        )
        base = select(orm.DeliveryOutcome).where(clause)
        count = select(func.count()).select_from(orm.DeliveryOutcome).where(clause)
        if horizon_days is not None:
            base = base.where(orm.DeliveryOutcome.horizon_days == horizon_days)
            count = count.where(orm.DeliveryOutcome.horizon_days == horizon_days)
        rows, total = self._paginate(
            base.order_by(
                orm.DeliveryOutcome.prediction_cutoff_at.asc(),
                orm.DeliveryOutcome.delivery_outcome_id.asc(),
            ),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.DeliveryOutcome, rows, total, limit, offset)

    def list_for_horizon(
        self,
        ctx: TenantContext,
        horizon_days: int,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dm.DeliveryOutcome]:
        """All outcomes for a horizon, including censored/unlabeled."""
        limit = max(1, min(limit, _MAX_HORIZON_LIST))
        offset = max(0, offset)
        rows = self._session.scalars(
            select(orm.DeliveryOutcome)
            .where(
                orm.DeliveryOutcome.tenant_id == ctx.tenant_id,
                orm.DeliveryOutcome.horizon_days == horizon_days,
            )
            .order_by(
                orm.DeliveryOutcome.prediction_cutoff_at.asc(),
                orm.DeliveryOutcome.delivery_outcome_id.asc(),
            )
            .offset(offset)
            .limit(limit)
        ).all()
        return [_to_dto(dm.DeliveryOutcome, row) for row in rows]

    def list_outcomes(
        self,
        ctx: TenantContext,
        *,
        verification_status: VerificationStatus | str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.DeliveryOutcome]:
        base = select(orm.DeliveryOutcome).where(orm.DeliveryOutcome.tenant_id == ctx.tenant_id)
        count = (
            select(func.count())
            .select_from(orm.DeliveryOutcome)
            .where(orm.DeliveryOutcome.tenant_id == ctx.tenant_id)
        )
        if verification_status is not None:
            status_value = _enum_value(verification_status)
            base = base.where(orm.DeliveryOutcome.verification_status == status_value)
            count = count.where(orm.DeliveryOutcome.verification_status == status_value)
        rows, total = self._paginate(
            base.order_by(orm.DeliveryOutcome.created_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.DeliveryOutcome, rows, total, limit, offset)

    def count_by_category(self, ctx: TenantContext) -> dict[str, int]:
        rows = self._session.execute(
            select(orm.DeliveryOutcome.outcome_category, func.count())
            .where(orm.DeliveryOutcome.tenant_id == ctx.tenant_id)
            .group_by(orm.DeliveryOutcome.outcome_category)
            .order_by(orm.DeliveryOutcome.outcome_category.asc())
        ).all()
        return {category: count for category, count in rows}

    def finalize(
        self,
        ctx: TenantContext,
        outcome_id: str,
        *,
        binary_label: int,
        outcome_category: OutcomeCategory | str,
        finalized_at: datetime,
    ) -> dm.DeliveryOutcome:
        row = self._tenant_get(
            orm.DeliveryOutcome,
            orm.DeliveryOutcome.delivery_outcome_id,
            outcome_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Delivery outcome not found for this tenant")
        if row.finalized_at is not None:
            raise EnterpriseConflictError("Cannot mutate finalized outcome labels")
        row.binary_label = binary_label
        row.outcome_category = _enum_value(outcome_category)
        row.finalized_at = _aware(finalized_at) or finalized_at
        row.updated_at = _utcnow()
        self._session.flush()
        return _to_dto(dm.DeliveryOutcome, row)

    def count(self, ctx: TenantContext) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(orm.DeliveryOutcome)
                .where(orm.DeliveryOutcome.tenant_id == ctx.tenant_id)
            )
            or 0
        )


class PredictionFeatureSnapshotRepository(_PredictionTenantRepository):
    def insert(
        self, ctx: TenantContext, snapshot: dm.PredictionFeatureSnapshot
    ) -> dm.PredictionFeatureSnapshot:
        with self._insert_guard("Feature snapshot already exists for this natural key"):
            self._session.add(orm.PredictionFeatureSnapshot(**_dump(snapshot, ctx)))
        return snapshot

    def get(self, ctx: TenantContext, snapshot_id: str) -> dm.PredictionFeatureSnapshot | None:
        row = self._tenant_get(
            orm.PredictionFeatureSnapshot,
            orm.PredictionFeatureSnapshot.prediction_feature_snapshot_id,
            snapshot_id,
            ctx,
        )
        return _to_dto(dm.PredictionFeatureSnapshot, row) if row else None

    def get_or_none(
        self,
        ctx: TenantContext,
        *,
        target_type: str,
        target_id: str,
        as_of_at: datetime,
        horizon_days: int,
        feature_schema_version: str,
    ) -> dm.PredictionFeatureSnapshot | None:
        row = self._session.scalar(
            select(orm.PredictionFeatureSnapshot).where(
                orm.PredictionFeatureSnapshot.tenant_id == ctx.tenant_id,
                orm.PredictionFeatureSnapshot.target_type == _enum_value(target_type),
                orm.PredictionFeatureSnapshot.target_id == target_id,
                orm.PredictionFeatureSnapshot.as_of_at == (_aware(as_of_at) or as_of_at),
                orm.PredictionFeatureSnapshot.horizon_days == horizon_days,
                orm.PredictionFeatureSnapshot.feature_schema_version == feature_schema_version,
            )
        )
        return _to_dto(dm.PredictionFeatureSnapshot, row) if row else None

    def get_by_hash(
        self, ctx: TenantContext, feature_hash: str
    ) -> dm.PredictionFeatureSnapshot | None:
        row = self._session.scalar(
            select(orm.PredictionFeatureSnapshot).where(
                orm.PredictionFeatureSnapshot.tenant_id == ctx.tenant_id,
                orm.PredictionFeatureSnapshot.feature_hash == feature_hash,
            )
        )
        return _to_dto(dm.PredictionFeatureSnapshot, row) if row else None

    def list_for_target(
        self,
        ctx: TenantContext,
        target_type: str,
        target_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.PredictionFeatureSnapshot]:
        type_value = _enum_value(target_type)
        clause = and_(
            orm.PredictionFeatureSnapshot.tenant_id == ctx.tenant_id,
            orm.PredictionFeatureSnapshot.target_type == type_value,
            orm.PredictionFeatureSnapshot.target_id == target_id,
        )
        base = select(orm.PredictionFeatureSnapshot).where(clause)
        count = select(func.count()).select_from(orm.PredictionFeatureSnapshot).where(clause)
        rows, total = self._paginate(
            base.order_by(orm.PredictionFeatureSnapshot.as_of_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.PredictionFeatureSnapshot, rows, total, limit, offset)

    def count(self, ctx: TenantContext) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(orm.PredictionFeatureSnapshot)
                .where(orm.PredictionFeatureSnapshot.tenant_id == ctx.tenant_id)
            )
            or 0
        )


class PredictionDatasetManifestRepository(_PredictionTenantRepository):
    def insert(
        self, ctx: TenantContext, manifest: dm.PredictionDatasetManifest
    ) -> dm.PredictionDatasetManifest:
        with self._insert_guard("Dataset manifest already exists for this tenant"):
            self._session.add(orm.PredictionDatasetManifest(**_dump(manifest, ctx)))
        return manifest

    def get(self, ctx: TenantContext, manifest_id: str) -> dm.PredictionDatasetManifest | None:
        row = self._tenant_get(
            orm.PredictionDatasetManifest,
            orm.PredictionDatasetManifest.prediction_dataset_manifest_id,
            manifest_id,
            ctx,
        )
        return _to_dto(dm.PredictionDatasetManifest, row) if row else None

    def get_by_hash(
        self, ctx: TenantContext, dataset_hash: str
    ) -> dm.PredictionDatasetManifest | None:
        row = self._session.scalar(
            select(orm.PredictionDatasetManifest).where(
                orm.PredictionDatasetManifest.tenant_id == ctx.tenant_id,
                orm.PredictionDatasetManifest.dataset_hash == dataset_hash,
            )
        )
        return _to_dto(dm.PredictionDatasetManifest, row) if row else None

    def list(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> Page[dm.PredictionDatasetManifest]:
        base = select(orm.PredictionDatasetManifest).where(
            orm.PredictionDatasetManifest.tenant_id == ctx.tenant_id
        )
        count = (
            select(func.count())
            .select_from(orm.PredictionDatasetManifest)
            .where(orm.PredictionDatasetManifest.tenant_id == ctx.tenant_id)
        )
        rows, total = self._paginate(
            base.order_by(orm.PredictionDatasetManifest.generated_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.PredictionDatasetManifest, rows, total, limit, offset)

    def count(self, ctx: TenantContext) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(orm.PredictionDatasetManifest)
                .where(orm.PredictionDatasetManifest.tenant_id == ctx.tenant_id)
            )
            or 0
        )


class PredictionModelRepository(_PredictionTenantRepository):
    def insert(self, ctx: TenantContext, model: dm.PredictionModel) -> dm.PredictionModel:
        with self._insert_guard("Prediction model already exists for this tenant"):
            self._session.add(orm.PredictionModel(**_dump(model, ctx)))
        return model

    def get(self, ctx: TenantContext, model_id: str) -> dm.PredictionModel | None:
        row = self._tenant_get(
            orm.PredictionModel,
            orm.PredictionModel.prediction_model_id,
            model_id,
            ctx,
        )
        return _to_dto(dm.PredictionModel, row) if row else None

    def update(self, ctx: TenantContext, model: dm.PredictionModel) -> dm.PredictionModel:
        """Apply state-transition fields from the DTO onto the persisted row."""
        row = self._tenant_get(
            orm.PredictionModel,
            orm.PredictionModel.prediction_model_id,
            model.prediction_model_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Prediction model not found for this tenant")
        payload = _dump(model, ctx)
        for key, value in payload.items():
            if key in {"prediction_model_id", "tenant_id", "created_at"}:
                continue
            if key in {"promoted_at", "retired_at", "trained_at"} and value is not None:
                value = _aware(value) or value
            setattr(row, key, value)
        self._session.flush()
        return _to_dto(dm.PredictionModel, row)

    def set_state(
        self,
        ctx: TenantContext,
        model_id: str,
        state: ModelState | str,
        *,
        promoted_at: datetime | None = None,
        retired_at: datetime | None = None,
    ) -> dm.PredictionModel:
        row = self._tenant_get(
            orm.PredictionModel,
            orm.PredictionModel.prediction_model_id,
            model_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Prediction model not found for this tenant")
        row.model_state = _enum_value(state)
        if promoted_at is not None:
            row.promoted_at = _aware(promoted_at) or promoted_at
        if retired_at is not None:
            row.retired_at = _aware(retired_at) or retired_at
        self._session.flush()
        return _to_dto(dm.PredictionModel, row)

    def list(
        self,
        ctx: TenantContext,
        *,
        model_state: ModelState | str | None = None,
        horizon_days: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.PredictionModel]:
        base = select(orm.PredictionModel).where(orm.PredictionModel.tenant_id == ctx.tenant_id)
        count = (
            select(func.count())
            .select_from(orm.PredictionModel)
            .where(orm.PredictionModel.tenant_id == ctx.tenant_id)
        )
        if model_state is not None:
            state_value = _enum_value(model_state)
            base = base.where(orm.PredictionModel.model_state == state_value)
            count = count.where(orm.PredictionModel.model_state == state_value)
        if horizon_days is not None:
            base = base.where(orm.PredictionModel.horizon_days == horizon_days)
            count = count.where(orm.PredictionModel.horizon_days == horizon_days)
        rows, total = self._paginate(
            base.order_by(orm.PredictionModel.trained_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.PredictionModel, rows, total, limit, offset)

    def get_active(
        self,
        ctx: TenantContext,
        *,
        target_definition: str,
        horizon_days: int,
        usage_scope: ModelUsageScope | str,
    ) -> dm.PredictionModel | None:
        row = self._session.scalar(
            select(orm.PredictionModel)
            .where(
                orm.PredictionModel.tenant_id == ctx.tenant_id,
                orm.PredictionModel.target_definition == target_definition,
                orm.PredictionModel.horizon_days == horizon_days,
                orm.PredictionModel.usage_scope == _enum_value(usage_scope),
                orm.PredictionModel.model_state == ModelState.ACTIVE.value,
            )
            .order_by(orm.PredictionModel.promoted_at.desc())
            .limit(1)
        )
        return _to_dto(dm.PredictionModel, row) if row else None

    def list_active_for_update(
        self,
        ctx: TenantContext,
        *,
        target_definition: str,
        horizon_days: int,
        usage_scope: ModelUsageScope | str,
    ) -> list[dm.PredictionModel]:
        """Active models for a scope, locked when the dialect supports FOR UPDATE."""
        query = select(orm.PredictionModel).where(
            orm.PredictionModel.tenant_id == ctx.tenant_id,
            orm.PredictionModel.target_definition == target_definition,
            orm.PredictionModel.horizon_days == horizon_days,
            orm.PredictionModel.usage_scope == _enum_value(usage_scope),
            orm.PredictionModel.model_state == ModelState.ACTIVE.value,
        )
        if self._supports_for_update():
            query = query.with_for_update()
        rows = self._session.scalars(
            query.order_by(orm.PredictionModel.prediction_model_id.asc())
        ).all()
        return [_to_dto(dm.PredictionModel, row) for row in rows]

    def count(self, ctx: TenantContext, *, model_state: ModelState | str | None = None) -> int:
        query = (
            select(func.count())
            .select_from(orm.PredictionModel)
            .where(orm.PredictionModel.tenant_id == ctx.tenant_id)
        )
        if model_state is not None:
            query = query.where(orm.PredictionModel.model_state == _enum_value(model_state))
        return self._session.scalar(query) or 0


class PredictionModelEvaluationRepository(_PredictionTenantRepository):
    def insert(
        self, ctx: TenantContext, evaluation: dm.PredictionModelEvaluation
    ) -> dm.PredictionModelEvaluation:
        with self._insert_guard("Model evaluation already exists for this tenant"):
            self._session.add(orm.PredictionModelEvaluation(**_dump(evaluation, ctx)))
        return evaluation

    def get(self, ctx: TenantContext, evaluation_id: str) -> dm.PredictionModelEvaluation | None:
        row = self._tenant_get(
            orm.PredictionModelEvaluation,
            orm.PredictionModelEvaluation.prediction_model_evaluation_id,
            evaluation_id,
            ctx,
        )
        return _to_dto(dm.PredictionModelEvaluation, row) if row else None

    def list_for_model(
        self,
        ctx: TenantContext,
        model_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.PredictionModelEvaluation]:
        clause = and_(
            orm.PredictionModelEvaluation.tenant_id == ctx.tenant_id,
            orm.PredictionModelEvaluation.prediction_model_id == model_id,
        )
        base = select(orm.PredictionModelEvaluation).where(clause)
        count = select(func.count()).select_from(orm.PredictionModelEvaluation).where(clause)
        rows, total = self._paginate(
            base.order_by(orm.PredictionModelEvaluation.evaluated_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.PredictionModelEvaluation, rows, total, limit, offset)

    def list(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> Page[dm.PredictionModelEvaluation]:
        base = select(orm.PredictionModelEvaluation).where(
            orm.PredictionModelEvaluation.tenant_id == ctx.tenant_id
        )
        count = (
            select(func.count())
            .select_from(orm.PredictionModelEvaluation)
            .where(orm.PredictionModelEvaluation.tenant_id == ctx.tenant_id)
        )
        rows, total = self._paginate(
            base.order_by(orm.PredictionModelEvaluation.evaluated_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.PredictionModelEvaluation, rows, total, limit, offset)

    def count(self, ctx: TenantContext) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(orm.PredictionModelEvaluation)
                .where(orm.PredictionModelEvaluation.tenant_id == ctx.tenant_id)
            )
            or 0
        )


class PredictionRunRepository(_PredictionTenantRepository):
    def insert(self, ctx: TenantContext, run: dm.PredictionRun) -> dm.PredictionRun:
        with self._insert_guard("Prediction run already exists for this tenant"):
            self._session.add(orm.PredictionRun(**_dump(run, ctx)))
        return run

    def get(self, ctx: TenantContext, run_id: str) -> dm.PredictionRun | None:
        row = self._tenant_get(
            orm.PredictionRun,
            orm.PredictionRun.prediction_run_id,
            run_id,
            ctx,
        )
        return _to_dto(dm.PredictionRun, row) if row else None

    def update(self, ctx: TenantContext, run: dm.PredictionRun) -> dm.PredictionRun:
        row = self._tenant_get(
            orm.PredictionRun,
            orm.PredictionRun.prediction_run_id,
            run.prediction_run_id,
            ctx,
        )
        if row is None:
            raise EnterpriseNotFoundError("Prediction run not found for this tenant")
        payload = _dump(run, ctx)
        for key, value in payload.items():
            if key in {"prediction_run_id", "tenant_id", "created_at"}:
                continue
            if key in {"as_of_at", "started_at", "completed_at"} and value is not None:
                value = _aware(value) or value
            setattr(row, key, value)
        self._session.flush()
        return _to_dto(dm.PredictionRun, row)

    def list(
        self,
        ctx: TenantContext,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.PredictionRun]:
        base = select(orm.PredictionRun).where(orm.PredictionRun.tenant_id == ctx.tenant_id)
        count = (
            select(func.count())
            .select_from(orm.PredictionRun)
            .where(orm.PredictionRun.tenant_id == ctx.tenant_id)
        )
        if target_type is not None:
            type_value = _enum_value(target_type)
            base = base.where(orm.PredictionRun.target_type == type_value)
            count = count.where(orm.PredictionRun.target_type == type_value)
        if target_id is not None:
            base = base.where(orm.PredictionRun.target_id == target_id)
            count = count.where(orm.PredictionRun.target_id == target_id)
        rows, total = self._paginate(
            base.order_by(orm.PredictionRun.created_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.PredictionRun, rows, total, limit, offset)

    def count(self, ctx: TenantContext) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(orm.PredictionRun)
                .where(orm.PredictionRun.tenant_id == ctx.tenant_id)
            )
            or 0
        )


class DeliveryPredictionRepository(_PredictionTenantRepository):
    def insert(
        self, ctx: TenantContext, prediction: dm.DeliveryPrediction
    ) -> dm.DeliveryPrediction:
        with self._insert_guard("Delivery prediction already exists for this tenant"):
            self._session.add(orm.DeliveryPrediction(**_dump(prediction, ctx)))
        return prediction

    def get(self, ctx: TenantContext, prediction_id: str) -> dm.DeliveryPrediction | None:
        row = self._tenant_get(
            orm.DeliveryPrediction,
            orm.DeliveryPrediction.delivery_prediction_id,
            prediction_id,
            ctx,
        )
        return _to_dto(dm.DeliveryPrediction, row) if row else None

    def get_by_hash(self, ctx: TenantContext, prediction_hash: str) -> dm.DeliveryPrediction | None:
        row = self._session.scalar(
            select(orm.DeliveryPrediction).where(
                orm.DeliveryPrediction.tenant_id == ctx.tenant_id,
                orm.DeliveryPrediction.prediction_hash == prediction_hash,
            )
        )
        return _to_dto(dm.DeliveryPrediction, row) if row else None

    def list_for_target(
        self,
        ctx: TenantContext,
        target_type: str,
        target_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Page[dm.DeliveryPrediction]:
        type_value = _enum_value(target_type)
        clause = and_(
            orm.DeliveryPrediction.tenant_id == ctx.tenant_id,
            orm.DeliveryPrediction.target_type == type_value,
            orm.DeliveryPrediction.target_id == target_id,
        )
        base = select(orm.DeliveryPrediction).where(clause)
        count = select(func.count()).select_from(orm.DeliveryPrediction).where(clause)
        rows, total = self._paginate(
            base.order_by(orm.DeliveryPrediction.created_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.DeliveryPrediction, rows, total, limit, offset)

    def list(
        self, ctx: TenantContext, *, limit: int = 20, offset: int = 0
    ) -> Page[dm.DeliveryPrediction]:
        base = select(orm.DeliveryPrediction).where(
            orm.DeliveryPrediction.tenant_id == ctx.tenant_id
        )
        count = (
            select(func.count())
            .select_from(orm.DeliveryPrediction)
            .where(orm.DeliveryPrediction.tenant_id == ctx.tenant_id)
        )
        rows, total = self._paginate(
            base.order_by(orm.DeliveryPrediction.created_at.desc()),
            count,
            limit=limit,
            offset=offset,
        )
        return _page(dm.DeliveryPrediction, rows, total, limit, offset)

    def count(self, ctx: TenantContext) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(orm.DeliveryPrediction)
                .where(orm.DeliveryPrediction.tenant_id == ctx.tenant_id)
            )
            or 0
        )

    def latest_for_target(
        self, ctx: TenantContext, target_type: str, target_id: str
    ) -> dm.DeliveryPrediction | None:
        row = self._session.scalar(
            select(orm.DeliveryPrediction)
            .where(
                orm.DeliveryPrediction.tenant_id == ctx.tenant_id,
                orm.DeliveryPrediction.target_type == _enum_value(target_type),
                orm.DeliveryPrediction.target_id == target_id,
            )
            .order_by(orm.DeliveryPrediction.created_at.desc())
            .limit(1)
        )
        return _to_dto(dm.DeliveryPrediction, row) if row else None


class PredictionFactorRepository(_PredictionTenantRepository):
    def insert(self, ctx: TenantContext, factor: dm.PredictionFactor) -> dm.PredictionFactor:
        with self._insert_guard("Prediction factor already exists for this tenant"):
            self._session.add(orm.PredictionFactor(**_dump(factor, ctx)))
        return factor

    def insert_many(
        self, ctx: TenantContext, factors: list[dm.PredictionFactor]
    ) -> list[dm.PredictionFactor]:
        if not factors:
            return []
        with self._insert_guard("Prediction factor already exists for this tenant"):
            for factor in factors:
                self._session.add(orm.PredictionFactor(**_dump(factor, ctx)))
        return factors

    def list_for_prediction(
        self,
        ctx: TenantContext,
        delivery_prediction_id: str,
        *,
        limit: int = 8,
    ) -> list[dm.PredictionFactor]:
        limit = max(1, min(limit, 8))
        # Ensure the parent prediction is visible to this tenant.
        parent = self._tenant_get(
            orm.DeliveryPrediction,
            orm.DeliveryPrediction.delivery_prediction_id,
            delivery_prediction_id,
            ctx,
        )
        if parent is None:
            raise CrossTenantAccessError(
                f"Referenced delivery prediction '{delivery_prediction_id}' "
                "is not visible to this tenant"
            )
        rows = self._session.scalars(
            select(orm.PredictionFactor)
            .where(
                orm.PredictionFactor.tenant_id == ctx.tenant_id,
                orm.PredictionFactor.delivery_prediction_id == delivery_prediction_id,
            )
            .order_by(orm.PredictionFactor.rank.asc())
            .limit(limit)
        ).all()
        return [_to_dto(dm.PredictionFactor, row) for row in rows]
