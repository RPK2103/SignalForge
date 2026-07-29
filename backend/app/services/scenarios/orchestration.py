"""Scenario orchestration facade for CLI/API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.scenario_constants import (
    DEFAULT_HORIZON_DAYS,
    MIN_WATCH_INTERVAL_MINUTES,
    SCENARIO_SCHEMA_VERSION,
)
from app.domain.scenario_enums import (
    ComparisonDimension,
    ScenarioKind,
    ScenarioLifecycleState,
    ScenarioRunMode,
    ScenarioTargetType,
    ScenarioWatchMode,
)
from app.domain.scenario_models import (
    ScenarioComparisonResult,
    ScenarioDefinition,
    ScenarioDueEvaluationSummary,
    ScenarioExecutionBundle,
    ScenarioHealth,
    ScenarioVersion,
    ScenarioWatch,
    ScenarioWatchEvaluationResult,
    validate_horizon,
)
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseNotFoundError
from app.services.scenarios.comparison import ScenarioComparisonService
from app.services.scenarios.execution import ScenarioExecutionService
from app.services.scenarios.validation import normalize_assumptions, specification_hash
from app.services.scenarios.watches import ScenarioWatchService

logger = logging.getLogger("signalforge.scenarios")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScenarioOrchestrationService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._execution = ScenarioExecutionService(uow)
        self._watches = ScenarioWatchService(uow)
        self._comparison = ScenarioComparisonService(uow)

    def create_definition(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str,
        target_type: ScenarioTargetType | str,
        target_id: str,
        scenario_kind: ScenarioKind | str,
    ) -> ScenarioDefinition:
        if isinstance(target_type, str):
            target_type = ScenarioTargetType(target_type)
        if isinstance(scenario_kind, str):
            scenario_kind = ScenarioKind(scenario_kind)
        self._require_target(ctx, target_type, target_id)
        definition_id = build_entity_id(
            "sdef", ctx.tenant_id, name, target_type.value, target_id, scenario_kind.value
        )
        definition = ScenarioDefinition(
            tenant_id=ctx.tenant_id,
            scenario_definition_id=definition_id,
            name=name,
            description=description or "",
            target_type=target_type,
            target_id=target_id,
            scenario_kind=scenario_kind,
            lifecycle_state=ScenarioLifecycleState.ACTIVE,
            current_version=0,
        )
        created = self._uow.scenario_definitions.create(ctx, definition)
        logger.info(
            "scenario.created tenant_id=%s definition_id=%s kind=%s",
            ctx.tenant_id,
            created.scenario_definition_id,
            scenario_kind.value,
        )
        return created

    def create_version(
        self,
        ctx: TenantContext,
        *,
        scenario_definition_id: str,
        assumptions: dict[str, Any],
        effective_from: datetime | None = None,
        created_by_context: str = "cli",
    ) -> ScenarioVersion:
        definition = self._uow.scenario_definitions.require(ctx, scenario_definition_id)
        normalized = normalize_assumptions(definition.scenario_kind, assumptions)
        self._validate_subjects(ctx, normalized)
        spec_hash = specification_hash(
            tenant_id=ctx.tenant_id,
            scenario_kind=definition.scenario_kind,
            target_type=definition.target_type.value
            if hasattr(definition.target_type, "value")
            else str(definition.target_type),
            target_id=definition.target_id,
            assumptions=normalized,
        )
        existing = self._uow.scenario_versions.get_by_spec_hash(ctx, spec_hash)
        if existing is not None:
            return existing

        next_version = int(definition.current_version) + 1
        version_id = build_entity_id(
            "sver", ctx.tenant_id, definition.scenario_definition_id, str(next_version), spec_hash
        )
        version = ScenarioVersion(
            tenant_id=ctx.tenant_id,
            scenario_version_id=version_id,
            scenario_definition_id=definition.scenario_definition_id,
            version_number=next_version,
            scenario_schema_version=SCENARIO_SCHEMA_VERSION,
            assumptions=normalized,
            effective_from=effective_from or _utcnow(),
            created_by_context=created_by_context,
            specification_hash=spec_hash,
        )
        created = self._uow.scenario_versions.create(ctx, version)
        self._uow.scenario_definitions.set_current_version(
            ctx, definition.scenario_definition_id, next_version
        )
        logger.info(
            "scenario.version.created tenant_id=%s version_id=%s number=%s",
            ctx.tenant_id,
            created.scenario_version_id,
            next_version,
        )
        return created

    def run(
        self,
        ctx: TenantContext,
        *,
        scenario_version_id: str,
        as_of_at: datetime | None = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> ScenarioExecutionBundle:
        horizon_days = validate_horizon(horizon_days)
        return self._execution.execute(
            ctx,
            scenario_version_id=scenario_version_id,
            as_of_at=as_of_at,
            horizon_days=horizon_days,
            run_mode=ScenarioRunMode.MANUAL,
        )

    def compare(
        self,
        ctx: TenantContext,
        run_ids: list[str],
        *,
        sort_dimension: ComparisonDimension | str,
        descending: bool = True,
    ) -> ScenarioComparisonResult:
        result = self._comparison.compare(
            ctx, run_ids, sort_dimension=sort_dimension, descending=descending
        )
        logger.info(
            "scenario.comparison.completed tenant_id=%s runs=%s dimension=%s",
            ctx.tenant_id,
            len(run_ids),
            result.sort_dimension.value,
        )
        return result

    def create_watch(
        self,
        ctx: TenantContext,
        *,
        scenario_version_id: str,
        watch_mode: ScenarioWatchMode | str = ScenarioWatchMode.ON_CHANGE,
        minimum_interval_minutes: int = MIN_WATCH_INTERVAL_MINUTES,
    ) -> ScenarioWatch:
        if isinstance(watch_mode, str):
            watch_mode = ScenarioWatchMode(watch_mode)
        return self._watches.create_watch(
            ctx,
            scenario_version_id=scenario_version_id,
            watch_mode=watch_mode,
            minimum_interval_minutes=minimum_interval_minutes,
        )

    def pause_watch(self, ctx: TenantContext, watch_id: str) -> ScenarioWatch:
        return self._watches.pause(ctx, watch_id)

    def resume_watch(self, ctx: TenantContext, watch_id: str) -> ScenarioWatch:
        return self._watches.resume(ctx, watch_id)

    def evaluate_watch(
        self,
        ctx: TenantContext,
        watch_id: str,
        *,
        as_of_at: datetime | None = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        force: bool = False,
    ) -> ScenarioWatchEvaluationResult:
        return self._watches.evaluate_watch(
            ctx,
            watch_id,
            as_of_at=as_of_at,
            horizon_days=horizon_days,
            force=force,
        )

    def evaluate_due(
        self,
        ctx: TenantContext,
        *,
        limit: int = 100,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> ScenarioDueEvaluationSummary:
        return self._watches.evaluate_due(ctx, limit=limit, horizon_days=horizon_days)

    def health(self, ctx: TenantContext) -> ScenarioHealth:
        definitions = self._uow.scenario_definitions.list(ctx, limit=1, offset=0)
        versions_total = 0
        # Bounded health scan via definition list pages.
        page = self._uow.scenario_definitions.list(ctx, limit=100, offset=0)
        for definition in page.items:
            versions_total += self._uow.scenario_versions.list_for_definition(
                ctx, definition.scenario_definition_id, limit=1, offset=0
            ).total
        # Runs approximated via first definition targets — use raw counts through pages.
        run_total = 0
        succeeded = 0
        fallback_runs = 0
        calibrated_runs = 0
        for definition in page.items:
            runs = self._uow.scenario_runs.list_for_definition(
                ctx, definition.scenario_definition_id, limit=100, offset=0
            )
            run_total += runs.total
            for run in runs.items:
                if run.state.value == "succeeded":
                    succeeded += 1
                result = self._uow.scenario_results.get_by_run(ctx, run.scenario_run_id)
                if result is None:
                    continue
                if result.baseline_estimate_kind.value == "uncalibrated_score":
                    fallback_runs += 1
                elif result.baseline_estimate_kind.value == "calibrated_probability":
                    calibrated_runs += 1
        watches = self._uow.scenario_watches.list(ctx, limit=100, offset=0)
        active = self._uow.scenario_watches.list(ctx, limit=100, offset=0, lifecycle_state="active")
        overlays = self._uow.scenario_feature_overlays.count(ctx)
        training_eligible = self._uow.scenario_feature_overlays.count_training_eligible(ctx)
        return ScenarioHealth(
            tenant_id=ctx.tenant_id,
            definition_count=definitions.total,
            version_count=versions_total,
            run_count=run_total,
            succeeded_run_count=succeeded,
            watch_count=watches.total,
            active_watch_count=active.total,
            overlay_count=overlays,
            training_eligible_overlay_count=training_eligible,
            fallback_estimate_run_count=fallback_runs,
            calibrated_estimate_run_count=calibrated_runs,
            status="ok" if training_eligible == 0 else "degraded",
        )

    def _require_target(
        self, ctx: TenantContext, target_type: ScenarioTargetType, target_id: str
    ) -> None:
        if target_type == ScenarioTargetType.PROJECT:
            if self._uow.initiatives_projects.get_project(ctx, target_id) is None:
                raise EnterpriseNotFoundError("Project not found for this tenant")
        else:
            if self._uow.initiatives_projects.get_initiative(ctx, target_id) is None:
                raise EnterpriseNotFoundError("Initiative not found for this tenant")

    def _validate_subjects(self, ctx: TenantContext, assumptions: dict[str, Any]) -> None:
        for change in assumptions.get("changes") or []:
            kind = change.get("kind")
            if kind == ScenarioKind.ENGINEER_UNAVAILABLE.value:
                if self._uow.engineer_profiles.get_profile(ctx, change["engineer_id"]) is None:
                    raise EnterpriseNotFoundError("Engineer not found for this tenant")
            elif kind == ScenarioKind.TEAM_CAPACITY_REDUCTION.value:
                if self._uow.organizations.get_team(ctx, change["team_id"]) is None:
                    raise EnterpriseNotFoundError("Team not found for this tenant")
            elif kind == ScenarioKind.CAPABILITY_UNAVAILABLE.value:
                caps = self._uow.enterprise_catalog.list_capabilities(ctx, limit=100, offset=0)
                ids = {c.capability_id for c in caps.items}
                if change["capability_id"] not in ids:
                    raise EnterpriseNotFoundError("Capability not found for this tenant")
            elif kind == ScenarioKind.REPOSITORY_UNAVAILABLE.value:
                if self._uow.delivery.get_repository(ctx, change["repository_id"]) is None:
                    raise EnterpriseNotFoundError("Repository not found for this tenant")
            elif kind == ScenarioKind.DEPENDENCY_DELAY.value:
                deps = self._uow.relationships.list_dependencies(ctx, limit=100, offset=0)
                ids = {d.dependency_id for d in deps.items}
                if change["dependency_id"] not in ids:
                    raise EnterpriseNotFoundError("Dependency not found for this tenant")
            elif kind == ScenarioKind.DEADLINE_COMPRESSION.value:
                if self._uow.initiatives_projects.get_project(ctx, change["project_id"]) is None:
                    raise EnterpriseNotFoundError("Project not found for this tenant")
            elif kind == ScenarioKind.INCIDENT_ESCALATION.value:
                # Accept incident/repository/project subject already validated structurally.
                if change.get("project_id"):
                    if (
                        self._uow.initiatives_projects.get_project(ctx, change["project_id"])
                        is None
                    ):
                        raise EnterpriseNotFoundError("Project not found for this tenant")
                if change.get("repository_id"):
                    if self._uow.delivery.get_repository(ctx, change["repository_id"]) is None:
                        raise EnterpriseNotFoundError("Repository not found for this tenant")
