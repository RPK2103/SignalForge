"""Source fingerprints for continuous scenario re-evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.db.models import enterprise as ent_orm
from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_constants import SCORECARD_VERSION, TARGET_DEFINITION
from app.domain.prediction_enums import ModelUsageScope
from app.domain.scenario_constants import SOURCE_FINGERPRINT_VERSION
from app.domain.scenario_enums import ScenarioTargetType, ScenarioTriggerReason
from app.domain.tenant_context import TenantContext
from app.services.persistence.snapshot_service import snapshot_hash


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _active_at(valid_from: datetime | None, valid_to: datetime | None, as_of: datetime) -> bool:
    """Interval semantics: valid_from <= t < valid_to (open end when valid_to is null)."""
    start = _aware(valid_from)
    end = _aware(valid_to)
    if start is not None and start > as_of:
        return False
    if end is not None and end <= as_of:
        return False
    return True


@dataclass(frozen=True)
class SourceFingerprintParts:
    fingerprint: str
    components: dict[str, str] = field(default_factory=dict)


def _component_hash(label: str, payload: Any) -> tuple[str, str]:
    return label, snapshot_hash(payload)


def _resolve_target_scope(
    uow: UnitOfWork,
    ctx: TenantContext,
    *,
    target_type: ScenarioTargetType,
    target_id: str,
) -> set[str]:
    """Entity IDs relevant to the watched target (excludes unrelated tenant state)."""
    scope: set[str] = {target_id}
    if target_type == ScenarioTargetType.PROJECT:
        project = uow.initiatives_projects.get_project(ctx, target_id)
        if project is None:
            return scope
        scope.add(project.enterprise_project_id)
        if project.initiative_id:
            scope.add(project.initiative_id)
        if project.owning_team_id:
            scope.add(project.owning_team_id)
        return scope

    initiative = uow.initiatives_projects.get_initiative(ctx, target_id)
    if initiative is None:
        return scope
    scope.add(initiative.initiative_id)
    projects = uow.session.scalars(
        select(ent_orm.EnterpriseProject).where(
            ent_orm.EnterpriseProject.tenant_id == ctx.tenant_id,
            ent_orm.EnterpriseProject.initiative_id == target_id,
        )
    ).all()
    for project in projects:
        scope.add(project.enterprise_project_id)
        if project.owning_team_id:
            scope.add(project.owning_team_id)
    return scope


def compute_source_fingerprint(
    uow: UnitOfWork,
    ctx: TenantContext,
    *,
    target_type: ScenarioTargetType | str,
    target_id: str,
    as_of_at: datetime,
    horizon_days: int,
    scenario_version_hash: str,
) -> SourceFingerprintParts:
    if isinstance(target_type, str):
        target_type = ScenarioTargetType(target_type)
    as_of = _aware(as_of_at)
    assert as_of is not None
    scope = _resolve_target_scope(uow, ctx, target_type=target_type, target_id=target_id)

    components: dict[str, str] = {}
    components.__setitem__(
        *_component_hash("scenario_version", {"specification_hash": scenario_version_hash})
    )

    target_updated: str | None = None
    if target_type == ScenarioTargetType.PROJECT:
        project = uow.initiatives_projects.get_project(ctx, target_id)
        if project is not None and getattr(project, "updated_at", None) is not None:
            target_updated = _aware(project.updated_at).isoformat()  # type: ignore[union-attr]
    else:
        initiative = uow.initiatives_projects.get_initiative(ctx, target_id)
        if initiative is not None and getattr(initiative, "updated_at", None) is not None:
            target_updated = _aware(initiative.updated_at).isoformat()  # type: ignore[union-attr]
    components.__setitem__(
        *_component_hash(
            "target",
            {
                "target_type": target_type.value,
                "target_id": target_id,
                "updated_at": target_updated,
            },
        )
    )

    ownerships = uow.relationships.list_ownerships(ctx, limit=500, offset=0)
    own_fp = sorted(
        [
            {
                "id": o.ownership_id,
                "owner": o.owner_id,
                "resource": o.resource_id,
                "allocation": o.allocation,
                "valid_from": o.valid_from.isoformat() if o.valid_from else None,
                "valid_to": o.valid_to.isoformat() if o.valid_to else None,
            }
            for o in ownerships.items
            if (o.owner_id in scope or o.resource_id in scope)
            and _active_at(o.valid_from, o.valid_to, as_of)
        ],
        key=lambda x: x["id"],
    )
    # Expand scope with owners/resources already attached to the target so
    # subsequent dependency/availability filters stay neighborhood-aware.
    for row in own_fp:
        scope.add(str(row["owner"]))
        scope.add(str(row["resource"]))
    components.__setitem__(*_component_hash("ownership", own_fp))

    deps = uow.relationships.list_dependencies(ctx, limit=500, offset=0)
    dep_fp = sorted(
        [
            {
                "id": d.dependency_id,
                "source": d.source_id,
                "target": d.target_id,
                "type": d.dependency_type.value
                if hasattr(d.dependency_type, "value")
                else str(d.dependency_type),
                "valid_from": d.valid_from.isoformat() if d.valid_from else None,
                "valid_to": d.valid_to.isoformat() if d.valid_to else None,
            }
            for d in deps.items
            if (d.source_id in scope or d.target_id in scope)
            and _active_at(d.valid_from, d.valid_to, as_of)
        ],
        key=lambda x: x["id"],
    )
    components.__setitem__(*_component_hash("dependency", dep_fp))

    avails = uow.relationships.list_availabilities(ctx, limit=500, offset=0)
    avail_fp = sorted(
        [
            {
                "id": a.availability_id,
                "subject": a.target_id,
                "pct": a.availability_percentage,
                "start": a.start_time.isoformat() if a.start_time else None,
                "end": a.end_time.isoformat() if a.end_time else None,
            }
            for a in avails.items
            if a.target_id in scope
            and _active_at(getattr(a, "start_time", None), getattr(a, "end_time", None), as_of)
        ],
        key=lambda x: x["id"],
    )
    components.__setitem__(*_component_hash("availability", avail_fp))

    projection = uow.graph_projection_runs.latest_succeeded(ctx)
    components.__setitem__(
        *_component_hash(
            "graph_projection",
            {
                "version": getattr(projection, "graph_projection_version", None)
                if projection
                else None,
                "run_id": getattr(projection, "graph_projection_run_id", None)
                if projection
                else None,
            },
        )
    )

    # Map graph nodes so findings can be limited to the target neighborhood.
    node_entity_by_id: dict[str, str] = {}
    offset = 0
    while True:
        page = uow.graph_nodes.list_nodes(ctx, limit=200, offset=offset, active_at=as_of)
        if not page.items:
            break
        for node in page.items:
            node_entity_by_id[node.graph_node_id] = node.entity_id
            if node.entity_id in scope:
                scope.add(node.graph_node_id)
        offset += len(page.items)
        if offset >= min(page.total, 2000) or len(page.items) < 200:
            break

    findings_page = uow.graph_findings.list_findings(ctx, limit=500, offset=0, active_at=as_of)
    finding_fp = sorted(
        [
            {
                "id": f.graph_finding_id,
                "type": f.finding_type.value
                if hasattr(f.finding_type, "value")
                else str(f.finding_type),
                "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                "primary": f.primary_node_id,
            }
            for f in findings_page.items
            if f.primary_node_id
            and (f.primary_node_id in scope or node_entity_by_id.get(f.primary_node_id) in scope)
        ],
        key=lambda x: x["id"],
    )
    components.__setitem__(*_component_hash("graph_findings", finding_fp))

    active_model = uow.prediction_models.get_active(
        ctx,
        target_definition=TARGET_DEFINITION,
        horizon_days=horizon_days,
        usage_scope=ModelUsageScope.DEMO,
    )
    if active_model is not None:
        pred_baseline = {
            "kind": "calibrated_model",
            "model_id": active_model.prediction_model_id,
            "version": getattr(active_model, "model_version", None),
        }
    else:
        pred_baseline = {"kind": "scorecard", "version": SCORECARD_VERSION}
    components.__setitem__(*_component_hash("prediction_baseline", pred_baseline))

    scope_list = sorted(scope)
    evidence_count = int(
        uow.session.scalar(
            select(func.count())
            .select_from(ent_orm.EvidenceSignal)
            .where(
                ent_orm.EvidenceSignal.tenant_id == ctx.tenant_id,
                ent_orm.EvidenceSignal.observed_at <= as_of,
                ent_orm.EvidenceSignal.subject_id.in_(scope_list) if scope_list else False,
            )
        )
        or 0
    )
    latest_observed = uow.session.scalar(
        select(func.max(ent_orm.EvidenceSignal.observed_at)).where(
            ent_orm.EvidenceSignal.tenant_id == ctx.tenant_id,
            ent_orm.EvidenceSignal.observed_at <= as_of,
            ent_orm.EvidenceSignal.subject_id.in_(scope_list) if scope_list else False,
        )
    )
    components.__setitem__(
        *_component_hash(
            "evidence",
            {
                "total": evidence_count,
                "latest_observed_at": _aware(latest_observed).isoformat()
                if latest_observed
                else None,
            },
        )
    )

    # Only freshness for data sources that contributed scoped evidence.
    source_ids = uow.session.scalars(
        select(ent_orm.EvidenceSignal.data_source_id)
        .where(
            ent_orm.EvidenceSignal.tenant_id == ctx.tenant_id,
            ent_orm.EvidenceSignal.observed_at <= as_of,
            ent_orm.EvidenceSignal.subject_id.in_(scope_list) if scope_list else False,
        )
        .distinct()
    ).all()
    source_id_set = {str(s) for s in source_ids}
    sources = uow.data_sources.list_data_sources(ctx, limit=50, offset=0)
    freshness = sorted(
        [
            {
                "id": s.data_source_id,
                "freshness": getattr(s, "last_success_at", None).isoformat()
                if getattr(s, "last_success_at", None)
                else None,
            }
            for s in sources.items
            if s.data_source_id in source_id_set
        ],
        key=lambda x: x["id"],
    )
    components.__setitem__(*_component_hash("source_freshness", freshness))

    # as_of_at is intentionally excluded from the aggregate fingerprint. Cutoff
    # filters components above; including wall-clock as_of made identical source
    # state appear changed on every watch evaluation. Run identity still embeds
    # as_of via ScenarioRun.run_input_hash.
    fingerprint = snapshot_hash(
        {
            "version": SOURCE_FINGERPRINT_VERSION,
            "tenant_id": ctx.tenant_id,
            "horizon_days": horizon_days,
            "target_type": target_type.value,
            "target_id": target_id,
            "components": {k: components[k] for k in sorted(components)},
        }
    )
    return SourceFingerprintParts(fingerprint=fingerprint, components=components)


def diff_fingerprint_components(
    previous: dict[str, str] | None,
    current: dict[str, str],
) -> tuple[list[str], ScenarioTriggerReason]:
    previous = previous or {}
    changed = sorted(k for k in set(previous) | set(current) if previous.get(k) != current.get(k))
    if not changed:
        return [], ScenarioTriggerReason.NO_RELEVANT_CHANGE
    reason_map = {
        "scenario_version": ScenarioTriggerReason.SCENARIO_VERSION_CHANGED,
        "target": ScenarioTriggerReason.TARGET_CHANGED,
        "ownership": ScenarioTriggerReason.OWNERSHIP_CHANGED,
        "dependency": ScenarioTriggerReason.DEPENDENCY_CHANGED,
        "availability": ScenarioTriggerReason.AVAILABILITY_CHANGED,
        "graph_projection": ScenarioTriggerReason.GRAPH_PROJECTION_CHANGED,
        "graph_findings": ScenarioTriggerReason.GRAPH_FINDINGS_CHANGED,
        "prediction_baseline": ScenarioTriggerReason.PREDICTION_BASELINE_CHANGED,
        "evidence": ScenarioTriggerReason.RELEVANT_EVIDENCE_CHANGED,
        "source_freshness": ScenarioTriggerReason.SOURCE_FRESHNESS_CHANGED,
    }
    for key in changed:
        if key in reason_map:
            return changed, reason_map[key]
    return changed, ScenarioTriggerReason.TARGET_CHANGED
