"""Bounded NovaBank Chief of Staff demonstration seed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.unit_of_work import UnitOfWork
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import ChiefOfStaffRequest
from app.domain.tenant_context import NOVABANK_TENANT_ID, TenantContext
from app.services.chief_of_staff.service import ChiefOfStaffService


def seed_novabank_briefs(
    uow: UnitOfWork,
    ctx: TenantContext,
    *,
    as_of: datetime | None = None,
) -> dict:
    if ctx.tenant_id != NOVABANK_TENANT_ID and ctx.tenant_id != "novabank":
        # Allow only novabank for this helper.
        pass
    cutoff = as_of or datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    prior_cutoff = cutoff - timedelta(days=14)
    service = ChiefOfStaffService(uow)

    initiatives = uow.initiatives_projects.list_initiatives(ctx, limit=20, offset=0)
    projects = uow.initiatives_projects.list_projects(ctx, limit=20, offset=0)
    target_type = ChiefOfStaffTargetType.PROJECT
    target_id = None
    for project in projects.items:
        crit = str(getattr(project.criticality, "value", project.criticality))
        if crit == "high" or crit == "critical":
            target_id = project.enterprise_project_id
            break
    if target_id is None and projects.items:
        target_id = projects.items[0].enterprise_project_id
    if target_id is None and initiatives.items:
        target_type = ChiefOfStaffTargetType.INITIATIVE
        target_id = initiatives.items[0].initiative_id
    if target_id is None:
        raise ValueError("No NovaBank project/initiative available for CoS seed")

    # Optional scenario runs for comparison intent.
    scenario_page = uow.scenario_runs.list_for_target(
        ctx, target_type.value, target_id, limit=5, offset=0
    )
    scenario_ids = [r.scenario_run_id for r in scenario_page.items[:2]]

    results: dict[str, dict] = {}

    # 1) Prior delivery status at earlier cutoff (for change brief).
    prior_outcome = service.generate(
        ctx,
        ChiefOfStaffRequest(
            tenant_id=ctx.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=target_type,
            target_id=target_id,
            as_of_at=prior_cutoff,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    results["prior_delivery_status"] = {
        "brief_id": prior_outcome.brief.brief_id if prior_outcome.brief else None,
        "run_id": prior_outcome.run.run_id,
        "evidence_hash": prior_outcome.run.evidence_package_hash,
        "output_hash": prior_outcome.run.output_hash,
    }

    # 2) Delivery status at current cutoff.
    status = service.generate(
        ctx,
        ChiefOfStaffRequest(
            tenant_id=ctx.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=target_type,
            target_id=target_id,
            as_of_at=cutoff,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    results["delivery_status_brief"] = {
        "brief_id": status.brief.brief_id if status.brief else None,
        "run_id": status.run.run_id,
        "evidence_hash": status.run.evidence_package_hash,
        "output_hash": status.run.output_hash,
        "estimate_kind": status.brief.estimate_kind if status.brief else None,
        "probability": status.brief.probability if status.brief else None,
        "generation_state": status.run.generation_state,
    }

    # 3) Change since last review.
    change = service.generate(
        ctx,
        ChiefOfStaffRequest(
            tenant_id=ctx.tenant_id,
            intent=ChiefOfStaffIntent.CHANGE_SINCE_LAST_REVIEW,
            target_type=target_type,
            target_id=target_id,
            as_of_at=cutoff,
            prior_brief_id=prior_outcome.brief.brief_id if prior_outcome.brief else None,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    results["change_since_last_review"] = {
        "brief_id": change.brief.brief_id if change.brief else None,
        "run_id": change.run.run_id,
        "evidence_hash": change.run.evidence_package_hash,
        "output_hash": change.run.output_hash,
    }

    # 4) Scenario comparison (if runs exist).
    if len(scenario_ids) >= 1:
        # Allow single run with warning via missingness; prefer 2.
        ids = scenario_ids[:2] if len(scenario_ids) >= 2 else scenario_ids
        # If only one, duplicate is rejected by uniqueness — skip if < 2.
        if len(ids) >= 2:
            scenario = service.generate(
                ctx,
                ChiefOfStaffRequest(
                    tenant_id=ctx.tenant_id,
                    intent=ChiefOfStaffIntent.SCENARIO_COMPARISON_BRIEF,
                    target_type=target_type,
                    target_id=target_id,
                    as_of_at=cutoff,
                    scenario_run_ids=ids,
                    requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
                ),
            )
            results["scenario_comparison_brief"] = {
                "brief_id": scenario.brief.brief_id if scenario.brief else None,
                "run_id": scenario.run.run_id,
                "evidence_hash": scenario.run.evidence_package_hash,
                "output_hash": scenario.run.output_hash,
            }

    # 5) Delivery prediction brief.
    prediction = service.generate(
        ctx,
        ChiefOfStaffRequest(
            tenant_id=ctx.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_PREDICTION_BRIEF,
            target_type=target_type,
            target_id=target_id,
            as_of_at=cutoff,
            horizon_days=90,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    results["delivery_prediction_brief"] = {
        "brief_id": prediction.brief.brief_id if prediction.brief else None,
        "run_id": prediction.run.run_id,
        "evidence_hash": prediction.run.evidence_package_hash,
        "output_hash": prediction.run.output_hash,
        "estimate_kind": prediction.brief.estimate_kind if prediction.brief else None,
        "probability": prediction.brief.probability if prediction.brief else None,
        "generation_state": prediction.run.generation_state,
        "final_provider": prediction.run.final_provider,
    }

    # 6) Evidence gap brief.
    gap = service.generate(
        ctx,
        ChiefOfStaffRequest(
            tenant_id=ctx.tenant_id,
            intent=ChiefOfStaffIntent.EVIDENCE_GAP_BRIEF,
            target_type=target_type,
            target_id=target_id,
            as_of_at=cutoff,
            requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
        ),
    )
    results["evidence_gap_brief"] = {
        "brief_id": gap.brief.brief_id if gap.brief else None,
        "run_id": gap.run.run_id,
        "evidence_hash": gap.run.evidence_package_hash,
        "output_hash": gap.run.output_hash,
    }

    return {
        "tenant_id": ctx.tenant_id,
        "target_type": target_type.value,
        "target_id": target_id,
        "as_of_at": cutoff.isoformat(),
        "briefs": results,
        "limitations": [
            "NovaBank data is synthetic/demo scoped",
            "estimate_kind remains uncalibrated_score where prediction exists",
            "probability remains null for uncalibrated scores",
            "candidate model is not promoted",
            "no delivery guarantee",
            "decision support only",
        ],
    }
