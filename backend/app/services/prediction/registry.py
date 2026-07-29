"""Prediction model registry lifecycle: get, list, promote, retire."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_constants import TARGET_DEFINITION
from app.domain.prediction_enums import (
    ModelState,
    ModelUsageScope,
    PredictionDataScope,
)
from app.domain.prediction_models import PredictionModel
from app.domain.tenant_context import TenantContext

logger = logging.getLogger("signalforge.prediction")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PredictionModelRegistry:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def get(self, ctx: TenantContext, model_id: str) -> PredictionModel | None:
        return self._uow.prediction_models.get(ctx, model_id)

    def list(
        self,
        ctx: TenantContext,
        *,
        state: ModelState | None = None,
        horizon_days: int | None = None,
        usage_scope: ModelUsageScope | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PredictionModel]:
        page = self._uow.prediction_models.list(
            ctx,
            model_state=state,
            horizon_days=horizon_days,
            limit=limit,
            offset=offset,
        )
        items = list(page.items)
        if usage_scope is not None:
            items = [m for m in items if m.usage_scope == usage_scope]
        return items

    def promote(
        self,
        ctx: TenantContext,
        model_id: str,
        *,
        confirm: bool = False,
    ) -> PredictionModel:
        if not confirm:
            raise ValueError("Model promotion requires confirm=True (explicit CLI action)")

        model = self._uow.prediction_models.get(ctx, model_id)
        if model is None:
            raise LookupError(f"Prediction model not found: {model_id}")

        if model.model_state != ModelState.VALIDATED:
            raise ValueError(
                f"Only validated models can be promoted; state={model.model_state.value}"
            )

        if model.data_scope == PredictionDataScope.SYNTHETIC:
            if model.usage_scope != ModelUsageScope.DEMO:
                model.usage_scope = ModelUsageScope.DEMO
            model.production_eligible = False

        if (
            model.usage_scope == ModelUsageScope.PRODUCTION
            and model.data_scope == PredictionDataScope.SYNTHETIC
        ):
            raise ValueError("Synthetic models cannot be promoted to production scope")

        now = _utcnow()
        try:
            self._retire_previous_active(
                ctx,
                target_definition=model.target_definition or TARGET_DEFINITION,
                horizon_days=model.horizon_days,
                usage_scope=model.usage_scope,
                except_model_id=model.prediction_model_id,
                retired_at=now,
            )

            model.model_state = ModelState.ACTIVE
            model.promoted_at = now
            if model.data_scope == PredictionDataScope.SYNTHETIC:
                model.production_eligible = False
                model.usage_scope = ModelUsageScope.DEMO

            updated = self._persist_model(ctx, model)
            self._uow.session.flush()
            self._assert_single_active(
                ctx,
                target_definition=updated.target_definition,
                horizon_days=updated.horizon_days,
                usage_scope=updated.usage_scope,
                expected_id=updated.prediction_model_id,
            )
        except IntegrityError as exc:
            self._uow.session.rollback()
            logger.warning(
                "prediction.model.promote_conflict tenant_id=%s model_id=%s error=%s",
                ctx.tenant_id,
                model_id,
                type(exc).__name__,
            )
            raise ValueError("Concurrent promotion conflict for active model scope") from exc

        logger.info(
            "prediction.model.promoted tenant_id=%s model_id=%s usage_scope=%s "
            "production_eligible=%s",
            ctx.tenant_id,
            updated.prediction_model_id,
            updated.usage_scope.value,
            updated.production_eligible,
        )
        return updated

    def retire(self, ctx: TenantContext, model_id: str) -> PredictionModel:
        model = self._uow.prediction_models.get(ctx, model_id)
        if model is None:
            raise LookupError(f"Prediction model not found: {model_id}")
        if model.model_state == ModelState.RETIRED:
            return model

        model.model_state = ModelState.RETIRED
        model.retired_at = _utcnow()
        updated = self._persist_model(ctx, model)
        logger.info(
            "prediction.model.retired tenant_id=%s model_id=%s",
            ctx.tenant_id,
            model_id,
        )
        return updated

    def get_active(
        self,
        ctx: TenantContext,
        *,
        horizon_days: int,
        usage_scope: ModelUsageScope = ModelUsageScope.DEMO,
        target_definition: str = TARGET_DEFINITION,
    ) -> PredictionModel | None:
        get_active = getattr(self._uow.prediction_models, "get_active", None)
        if callable(get_active):
            return get_active(
                ctx,
                target_definition=target_definition,
                horizon_days=horizon_days,
                usage_scope=usage_scope,
            )
        models = self.list(
            ctx,
            state=ModelState.ACTIVE,
            horizon_days=horizon_days,
            usage_scope=usage_scope,
            limit=10,
        )
        for model in models:
            if model.target_definition == target_definition:
                return model
        return None

    def _retire_previous_active(
        self,
        ctx: TenantContext,
        *,
        target_definition: str,
        horizon_days: int,
        usage_scope: ModelUsageScope,
        except_model_id: str,
        retired_at: datetime,
    ) -> None:
        lock_fn = getattr(self._uow.prediction_models, "list_active_for_update", None)
        if callable(lock_fn):
            try:
                actives = list(
                    lock_fn(
                        ctx,
                        target_definition=target_definition,
                        horizon_days=horizon_days,
                        usage_scope=usage_scope,
                    )
                )
            except TypeError:
                actives = list(lock_fn(ctx))
        else:
            actives = [
                m
                for m in self.list(
                    ctx,
                    state=ModelState.ACTIVE,
                    horizon_days=horizon_days,
                    usage_scope=usage_scope,
                    limit=50,
                )
                if m.target_definition == target_definition
            ]

        for active in actives:
            if active.prediction_model_id == except_model_id:
                continue
            active.model_state = ModelState.RETIRED
            active.retired_at = retired_at
            self._persist_model(ctx, active)
            logger.info(
                "prediction.model.auto_retired tenant_id=%s model_id=%s replaced_by=%s",
                ctx.tenant_id,
                active.prediction_model_id,
                except_model_id,
            )

    def _assert_single_active(
        self,
        ctx: TenantContext,
        *,
        target_definition: str,
        horizon_days: int,
        usage_scope: ModelUsageScope,
        expected_id: str,
    ) -> None:
        actives = [
            m
            for m in self.list(
                ctx,
                state=ModelState.ACTIVE,
                horizon_days=horizon_days,
                usage_scope=usage_scope,
                limit=20,
            )
            if m.target_definition == target_definition
        ]
        if len(actives) > 1:
            raise ValueError("Invariant violated: multiple active models in the same scope")
        if actives and actives[0].prediction_model_id != expected_id:
            raise ValueError("Active model mismatch after promotion")

    def _persist_model(self, ctx: TenantContext, model: PredictionModel) -> PredictionModel:
        update = getattr(self._uow.prediction_models, "update", None)
        if callable(update):
            return update(ctx, model)
        set_state = getattr(self._uow.prediction_models, "set_state", None)
        if callable(set_state):
            return set_state(
                ctx,
                model.prediction_model_id,
                model.model_state,
                promoted_at=model.promoted_at,
                retired_at=model.retired_at,
                usage_scope=model.usage_scope,
                production_eligible=model.production_eligible,
            )
        # Last resort: repositories that treat insert as upsert.
        return self._uow.prediction_models.insert(ctx, model)
