"""Cross-prompt intelligence materialization for NovaBank demo."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.unit_of_work import UnitOfWork
from app.demo.novabank.constants import AS_OF_AT, DATASET_VERSION, TENANT_ID
from app.demo.novabank.helpers import resolve_foundational_ids
from app.demo.novabank.specification import CANONICAL_SPEC
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import ChiefOfStaffRequest
from app.domain.tenant_context import TenantContext
from app.services.chief_of_staff.service import ChiefOfStaffService
from app.services.graph.analysis_service import GraphAnalysisService
from app.services.graph.projection_service import GraphProjectionService
from app.services.scenarios.orchestration import ScenarioOrchestrationService

_logger = logging.getLogger("app.demo.novabank.intelligence")


class MaterializationError(RuntimeError):
    """Raised when a required materialization stage fails."""

    def __init__(self, stage: str, cause: BaseException) -> None:
        self.stage = stage
        self.cause = cause
        super().__init__(f"materialization failed at {stage}: {type(cause).__name__}")


def materialize_intelligence(session: Session) -> dict[str, Any]:
    """Rebuild graph, run story scenarios, generate deterministic-fallback briefs.

    Graph rebuild is mandatory. A graph IntegrityError (or any projection failure)
    aborts materialization — callers must roll back and must not emit success.
    Does not promote candidate models. Mandatory path uses DETERMINISTIC_FALLBACK.
    Telemetry emits only low-cardinality fields (dataset version, phase, counts).
    """
    ctx = TenantContext.require(TENANT_ID)
    uow = UnitOfWork(session)
    ids = resolve_foundational_ids()
    result: dict[str, Any] = {
        "dataset_version": DATASET_VERSION,
        "graph_rebuilt": False,
        "graph_findings": 0,
        "scenarios_executed": 0,
        "briefs_generated": 0,
        "estimate_kinds": [],
        "errors": [],
        "ok": False,
    }

    # Graph rebuild is atomic with materialization success. Do not catch-and-
    # continue: partial projections must roll back with the caller UoW.
    try:
        projection = GraphProjectionService(uow)
        projection.full_rebuild(ctx)
        analysis = GraphAnalysisService(uow)
        run = analysis.analyze(ctx)
        result["graph_rebuilt"] = True
        finding_count = int(getattr(run, "finding_count", 0) or 0)
        if finding_count == 0:
            page = uow.graph_findings.list_findings(ctx, limit=1, offset=0)
            finding_count = int(getattr(page, "total", 0) or 0)
        result["graph_findings"] = finding_count
        _logger.info(
            "demo.materialize.graph dataset_version=%s findings=%s",
            DATASET_VERSION,
            result["graph_findings"],
        )
    except Exception as exc:
        result["errors"].append(f"graph:{type(exc).__name__}")
        _logger.warning("demo.materialize.graph_failed category=%s", type(exc).__name__)
        raise MaterializationError("graph", exc) from exc

    orch = ScenarioOrchestrationService(uow)
    defs = (
        orch.list_definitions(ctx, limit=50, offset=0)
        if hasattr(orch, "list_definitions")
        else None
    )
    if defs is None:
        page = uow.scenario_definitions.list(ctx, limit=50, offset=0)
        definition_items = page.items
    else:
        definition_items = defs.items if hasattr(defs, "items") else defs

    story_names = {s.scenario_name for s in CANONICAL_SPEC.stories}
    for definition in definition_items:
        if definition.name not in story_names:
            continue
        versions = uow.scenario_versions.list_for_definition(
            ctx, definition.scenario_definition_id, limit=5, offset=0
        )
        if not versions.items:
            continue
        version = versions.items[0]
        try:
            orch.run(ctx, scenario_version_id=version.scenario_version_id, as_of_at=AS_OF_AT)
            result["scenarios_executed"] += 1
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"scenario:{type(exc).__name__}")
            _logger.warning("demo.materialize.scenario_failed category=%s", type(exc).__name__)
            raise MaterializationError("scenario", exc) from exc

    cos = ChiefOfStaffService(uow)
    # All eight stories — including Story 7 concentrated ownership — via existing
    # grounded orchestrator with DETERMINISTIC_FALLBACK (no external LLM).
    brief_targets = [
        ("story-01", ChiefOfStaffTargetType.PROJECT, ids["proj:fraud-scoring-v2"]),
        ("story-02", ChiefOfStaffTargetType.PROJECT, ids["proj:rt-payments-rail"]),
        ("story-03", ChiefOfStaffTargetType.INITIATIVE, ids["init:azure-migration"]),
        ("story-04", ChiefOfStaffTargetType.PROJECT, ids["proj:copilot-orchestration"]),
        ("story-05", ChiefOfStaffTargetType.PROJECT, ids["proj:fraud-scoring-v2"]),
        ("story-06", ChiefOfStaffTargetType.PROJECT, ids["proj:slo-platform"]),
        ("story-07", ChiefOfStaffTargetType.PROJECT, ids["proj:fraud-scoring-v2"]),
        ("story-08", ChiefOfStaffTargetType.INITIATIVE, ids["init:payment-modernization"]),
    ]
    for _story_id, target_type, target_id in brief_targets:
        try:
            outcome = cos.generate(
                ctx,
                ChiefOfStaffRequest(
                    tenant_id=TENANT_ID,
                    intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
                    target_type=target_type,
                    target_id=target_id,
                    as_of_at=AS_OF_AT,
                    requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
                ),
            )
            result["briefs_generated"] += 1
            kind = outcome.brief.estimate_kind if outcome.brief else None
            if kind is not None:
                result["estimate_kinds"].append(str(kind))
            # Guardrail: never treat as probability in materialization output.
            if outcome.brief is not None and outcome.brief.probability is not None:
                result["errors"].append("brief_emitted_probability")
                raise MaterializationError("brief", RuntimeError("brief_emitted_probability"))
        except MaterializationError:
            raise
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"brief:{type(exc).__name__}")
            _logger.warning("demo.materialize.brief_failed category=%s", type(exc).__name__)
            raise MaterializationError("brief", exc) from exc

    if result["scenarios_executed"] < 8:
        raise MaterializationError(
            "scenario",
            RuntimeError(f"expected 8 story scenarios, got {result['scenarios_executed']}"),
        )
    if result["briefs_generated"] < 8:
        raise MaterializationError(
            "brief",
            RuntimeError(f"expected 8 story briefs, got {result['briefs_generated']}"),
        )

    session.flush()
    result["ok"] = True
    _logger.info(
        "demo.materialize.complete dataset_version=%s scenarios=%s briefs=%s",
        DATASET_VERSION,
        result["scenarios_executed"],
        result["briefs_generated"],
    )
    return result
