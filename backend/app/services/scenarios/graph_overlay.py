"""In-memory scenario graph overlay — never mutates Delivery Graph tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.db.unit_of_work import UnitOfWork
from app.domain.graph_enums import GraphFindingType
from app.domain.scenario_constants import (
    MAX_GRAPH_DEPTH,
    MAX_GRAPH_EDGES,
    MAX_GRAPH_NODES,
    MAX_RETURNED_PATHS,
    SCENARIO_GRAPH_OVERLAY_VERSION,
)
from app.domain.scenario_enums import ScenarioKind
from app.domain.tenant_context import TenantContext
from app.services.graph.algorithms import Adjacency, TraversalBounds, blast_radius_traversal
from app.services.persistence.snapshot_service import snapshot_hash


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class OverlayFinding:
    finding_key: str
    finding_type: str
    severity: str
    primary_node_id: str | None
    affected_node_ids: list[str] = field(default_factory=list)
    supporting_edge_ids: list[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class GraphOverlayResult:
    overlay_version: str = SCENARIO_GRAPH_OVERLAY_VERSION
    nodes_examined: int = 0
    edges_examined: int = 0
    truncated: bool = False
    baseline_findings: list[OverlayFinding] = field(default_factory=list)
    simulated_findings: list[OverlayFinding] = field(default_factory=list)
    findings_added: list[OverlayFinding] = field(default_factory=list)
    findings_removed: list[OverlayFinding] = field(default_factory=list)
    findings_worsened: list[OverlayFinding] = field(default_factory=list)
    findings_improved: list[OverlayFinding] = field(default_factory=list)
    impacted_node_ids: list[str] = field(default_factory=list)
    impacted_project_ids: list[str] = field(default_factory=list)
    impacted_initiative_ids: list[str] = field(default_factory=list)
    critical_initiative_ids: list[str] = field(default_factory=list)
    path_explanations: list[dict[str, Any]] = field(default_factory=list)
    ownership_concentration_delta: float = 0.0
    capability_concentration_delta: float = 0.0
    dependency_delay_days: int = 0
    blast_radius_node_count: int = 0
    assumption_ids: list[str] = field(default_factory=list)
    overlay_hash: str = ""


_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class ScenarioGraphOverlayEngine:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def apply(
        self,
        ctx: TenantContext,
        *,
        target_type: str,
        target_id: str,
        as_of_at: datetime,
        assumptions: dict[str, Any],
        baseline_finding_summaries: list[dict[str, Any]],
    ) -> GraphOverlayResult:
        as_of = _aware(as_of_at)
        changes = list(assumptions.get("changes") or [])
        assumption_ids = [
            snapshot_hash({"idx": i, "change": change})[:16] for i, change in enumerate(changes)
        ]

        # Bounded subgraph load (active at as_of).
        node_page = self._uow.graph_nodes.list_nodes(
            ctx, limit=min(100, MAX_GRAPH_NODES), offset=0, active_at=as_of
        )
        # Prefer traversal edges when available.
        try:
            edges = self._uow.graph_edges.list_active_edges_for_traversal(
                ctx, active_at=as_of, max_edges=MAX_GRAPH_EDGES
            )
        except TypeError:
            edge_page = self._uow.graph_edges.list_edges(
                ctx, limit=min(100, MAX_GRAPH_EDGES), offset=0, active_at=as_of
            )
            edges = list(edge_page.items)

        nodes_by_entity: dict[tuple[str, str], Any] = {}
        nodes_by_id: dict[str, Any] = {}
        for node in node_page.items:
            nodes_by_id[node.graph_node_id] = node
            key = (
                node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
                node.entity_id,
            )
            nodes_by_entity[key] = node

        # Expand via additional pages if totals exceed page (still bounded).
        if node_page.total > len(node_page.items):
            offset = len(node_page.items)
            while offset < min(node_page.total, MAX_GRAPH_NODES):
                more = self._uow.graph_nodes.list_nodes(
                    ctx, limit=100, offset=offset, active_at=as_of
                )
                if not more.items:
                    break
                for node in more.items:
                    nodes_by_id[node.graph_node_id] = node
                    key = (
                        node.node_type.value
                        if hasattr(node.node_type, "value")
                        else str(node.node_type),
                        node.entity_id,
                    )
                    nodes_by_entity[key] = node
                offset += len(more.items)

        target_node = nodes_by_entity.get((target_type, target_id))
        seed_node_ids: list[str] = []
        if target_node is not None:
            seed_node_ids.append(target_node.graph_node_id)

        deactivated_owner_ids: set[str] = set()
        deactivated_repo_ids: set[str] = set()
        deactivated_capability_ids: set[str] = set()
        delayed_dependency_ids: dict[str, int] = {}
        capacity_reductions: dict[str, int] = {}
        escalated_incidents: list[dict[str, Any]] = []
        deadline_compressions: dict[str, int] = {}

        for change in changes:
            kind = change.get("kind")
            if kind == ScenarioKind.ENGINEER_UNAVAILABLE.value:
                deactivated_owner_ids.add(change["engineer_id"])
                node = nodes_by_entity.get(
                    ("engineer", change["engineer_id"])
                ) or nodes_by_entity.get(("engineer_profile", change["engineer_id"]))
                if node:
                    seed_node_ids.append(node.graph_node_id)
            elif kind == ScenarioKind.TEAM_CAPACITY_REDUCTION.value:
                capacity_reductions[change["team_id"]] = int(change["reduction_percentage"])
                node = nodes_by_entity.get(("team", change["team_id"]))
                if node:
                    seed_node_ids.append(node.graph_node_id)
            elif kind == ScenarioKind.CAPABILITY_UNAVAILABLE.value:
                deactivated_capability_ids.add(change["capability_id"])
                node = nodes_by_entity.get(("capability", change["capability_id"]))
                if node:
                    seed_node_ids.append(node.graph_node_id)
            elif kind == ScenarioKind.REPOSITORY_UNAVAILABLE.value:
                deactivated_repo_ids.add(change["repository_id"])
                node = nodes_by_entity.get(("repository", change["repository_id"]))
                if node:
                    seed_node_ids.append(node.graph_node_id)
            elif kind == ScenarioKind.DEPENDENCY_DELAY.value:
                delayed_dependency_ids[change["dependency_id"]] = int(change["delay_days"])
            elif kind == ScenarioKind.DEADLINE_COMPRESSION.value:
                deadline_compressions[change["project_id"]] = int(change["days_reduced"])
                node = nodes_by_entity.get(("project", change["project_id"]))
                if node:
                    seed_node_ids.append(node.graph_node_id)
            elif kind == ScenarioKind.INCIDENT_ESCALATION.value:
                escalated_incidents.append(change)
                for key_name in ("incident_id", "repository_id", "project_id"):
                    if change.get(key_name):
                        for etype in ("incident", "repository", "project"):
                            node = nodes_by_entity.get((etype, change[key_name]))
                            if node:
                                seed_node_ids.append(node.graph_node_id)

        seed_node_ids = sorted(set(seed_node_ids))
        adj = Adjacency.from_edges(list(edges)[:MAX_GRAPH_EDGES])
        bounds = TraversalBounds(
            max_depth=MAX_GRAPH_DEPTH,
            max_nodes=MAX_GRAPH_NODES,
            max_edges=MAX_GRAPH_EDGES,
            max_paths=MAX_RETURNED_PATHS,
        ).validated()

        impacted: set[str] = set(seed_node_ids)
        paths: list[dict[str, Any]] = []
        blast_count = 0
        truncated = False
        initiative_node_ids = {
            n.graph_node_id
            for n in nodes_by_id.values()
            if (n.node_type.value if hasattr(n.node_type, "value") else str(n.node_type))
            == "initiative"
        }
        critical_initiative_node_ids: set[str] = set()
        for nid in initiative_node_ids:
            node = nodes_by_id[nid]
            initiative = self._uow.initiatives_projects.get_initiative(ctx, node.entity_id)
            if initiative is None:
                continue
            crit = (
                initiative.criticality.value
                if hasattr(initiative.criticality, "value")
                else str(initiative.criticality)
            )
            if crit == "critical":
                critical_initiative_node_ids.add(nid)

        for seed in seed_node_ids[:20]:
            radius, stats = blast_radius_traversal(
                adj,
                seed,
                bounds=bounds,
                initiative_node_ids=initiative_node_ids,
                critical_initiative_node_ids=critical_initiative_node_ids,
            )
            reached = list(radius.get("directly_affected_node_ids", [])) + list(
                radius.get("indirectly_affected_node_ids", [])
            )
            reached.extend(radius.get("affected_initiative_ids") or [])
            reached.extend(radius.get("affected_critical_initiative_ids") or [])
            blast_count = max(blast_count, len(set(reached)) + 1)
            impacted.update(reached)
            impacted.add(seed)
            if stats.truncated:
                truncated = True
            for path in list(radius.get("path_explanations") or [])[:MAX_RETURNED_PATHS]:
                node_ids = list(getattr(path, "node_ids", None) or [])
                edge_ids = list(getattr(path, "edge_ids", None) or [])
                paths.append(
                    {
                        "seed_node_id": seed,
                        "node_ids": node_ids[:50],
                        "edge_ids": edge_ids[:50],
                    }
                )

        # Map impacted nodes to projects/initiatives.
        project_ids: set[str] = set()
        initiative_ids: set[str] = set()
        critical_initiative_ids: set[str] = set()
        for nid in sorted(impacted)[:MAX_GRAPH_NODES]:
            node = nodes_by_id.get(nid)
            if node is None:
                continue
            et = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
            if et == "project":
                project_ids.add(node.entity_id)
            elif et == "initiative":
                initiative_ids.add(node.entity_id)

        for init_id in sorted(initiative_ids):
            initiative = self._uow.initiatives_projects.get_initiative(ctx, init_id)
            if initiative is None:
                continue
            crit = (
                initiative.criticality.value
                if hasattr(initiative.criticality, "value")
                else str(initiative.criticality)
            )
            if crit == "critical":
                critical_initiative_ids.add(init_id)

        baseline_findings = [
            OverlayFinding(
                finding_key=str(item.get("hash") or item["id"]),
                finding_type=str(item["type"]),
                severity=str(item["severity"]),
                primary_node_id=item.get("primary_node_id"),
                explanation="Baseline graph finding at as-of cutoff.",
            )
            for item in baseline_finding_summaries
        ]

        simulated = list(baseline_findings)
        ownership_delta = 0.0
        capability_delta = 0.0
        delay_days = sum(delayed_dependency_ids.values())

        if deactivated_owner_ids:
            ownership_delta += float(len(deactivated_owner_ids))
            for eng_id in sorted(deactivated_owner_ids):
                node = nodes_by_entity.get(("engineer", eng_id)) or nodes_by_entity.get(
                    ("engineer_profile", eng_id)
                )
                primary = node.graph_node_id if node else None
                simulated.append(
                    OverlayFinding(
                        finding_key=snapshot_hash(
                            {"type": "availability_blast_radius", "engineer_id": eng_id}
                        )[:24],
                        finding_type=GraphFindingType.AVAILABILITY_BLAST_RADIUS.value,
                        severity="high",
                        primary_node_id=primary,
                        affected_node_ids=sorted(impacted)[:50],
                        explanation=(
                            "This scenario increases ownership concentration because an "
                            "engineer is marked unavailable under explicit assumptions."
                        ),
                    )
                )
                simulated.append(
                    OverlayFinding(
                        finding_key=snapshot_hash(
                            {"type": "single_person_dependency", "engineer_id": eng_id}
                        )[:24],
                        finding_type=GraphFindingType.SINGLE_PERSON_DEPENDENCY.value,
                        severity="high",
                        primary_node_id=primary,
                        affected_node_ids=sorted(project_ids)[:50],
                        explanation=(
                            "This scenario increases single-person dependency exposure "
                            "along affected ownership paths."
                        ),
                    )
                )

        if deactivated_repo_ids:
            ownership_delta += 0.5 * len(deactivated_repo_ids)
            for repo_id in sorted(deactivated_repo_ids):
                node = nodes_by_entity.get(("repository", repo_id))
                simulated.append(
                    OverlayFinding(
                        finding_key=snapshot_hash(
                            {"type": "repository_concentration", "repository_id": repo_id}
                        )[:24],
                        finding_type=GraphFindingType.REPOSITORY_OWNERSHIP_CONCENTRATION.value,
                        severity="high",
                        primary_node_id=node.graph_node_id if node else None,
                        affected_node_ids=sorted(impacted)[:50],
                        explanation=(
                            "This scenario affects repository support paths while the "
                            "repository is marked unavailable."
                        ),
                    )
                )

        if deactivated_capability_ids:
            capability_delta += float(len(deactivated_capability_ids))
            for cap_id in sorted(deactivated_capability_ids):
                node = nodes_by_entity.get(("capability", cap_id))
                simulated.append(
                    OverlayFinding(
                        finding_key=snapshot_hash(
                            {"type": "capability_concentration", "capability_id": cap_id}
                        )[:24],
                        finding_type=GraphFindingType.CAPABILITY_OWNERSHIP_CONCENTRATION.value,
                        severity="high",
                        primary_node_id=node.graph_node_id if node else None,
                        affected_node_ids=sorted(impacted)[:50],
                        explanation=(
                            "This scenario increases capability concentration because a "
                            "required capability is marked unavailable."
                        ),
                    )
                )

        if capacity_reductions:
            ownership_delta += sum(v / 100.0 for v in capacity_reductions.values())
            for team_id, pct in sorted(capacity_reductions.items()):
                node = nodes_by_entity.get(("team", team_id))
                simulated.append(
                    OverlayFinding(
                        finding_key=snapshot_hash(
                            {"type": "team_capacity", "team_id": team_id, "pct": pct}
                        )[:24],
                        finding_type=GraphFindingType.CROSS_TEAM_DEPENDENCY.value,
                        severity="medium" if pct < 50 else "high",
                        primary_node_id=node.graph_node_id if node else None,
                        affected_node_ids=sorted(project_ids | initiative_ids)[:50],
                        explanation=(
                            f"This scenario reduces simulated team capacity by {pct}% and "
                            "affects cross-team dependency paths."
                        ),
                    )
                )

        if delayed_dependency_ids:
            for dep_id, days in sorted(delayed_dependency_ids.items()):
                simulated.append(
                    OverlayFinding(
                        finding_key=snapshot_hash(
                            {"type": "dependency_delay", "dependency_id": dep_id, "days": days}
                        )[:24],
                        finding_type=GraphFindingType.CROSS_TEAM_DEPENDENCY.value,
                        severity="medium" if days < 45 else "high",
                        primary_node_id=target_node.graph_node_id if target_node else None,
                        affected_node_ids=sorted(project_ids)[:50],
                        explanation=(
                            f"This scenario introduces a simulated dependency delay of {days} days."
                        ),
                    )
                )

        if escalated_incidents:
            for inc in escalated_incidents:
                severity = str(inc.get("simulated_severity") or "high")
                simulated.append(
                    OverlayFinding(
                        finding_key=snapshot_hash({"type": "incident_escalation", **inc})[:24],
                        finding_type=GraphFindingType.AVAILABILITY_BLAST_RADIUS.value,
                        severity=severity,
                        primary_node_id=target_node.graph_node_id if target_node else None,
                        affected_node_ids=sorted(impacted)[:50],
                        explanation=(
                            "This scenario escalates incident severity under explicit assumptions "
                            "and expands the affected blast radius."
                        ),
                    )
                )

        if deadline_compressions:
            for project_id, days in sorted(deadline_compressions.items()):
                node = nodes_by_entity.get(("project", project_id))
                simulated.append(
                    OverlayFinding(
                        finding_key=snapshot_hash(
                            {"type": "deadline_compression", "project_id": project_id, "days": days}
                        )[:24],
                        finding_type=GraphFindingType.CROSS_TEAM_DEPENDENCY.value,
                        severity="medium",
                        primary_node_id=node.graph_node_id if node else None,
                        affected_node_ids=[project_id],
                        explanation=(
                            f"This scenario compresses the project deadline by {days} days "
                            "under explicit assumptions."
                        ),
                    )
                )

        # Deduplicate simulated findings by key.
        sim_by_key = {f.finding_key: f for f in simulated}
        simulated = [sim_by_key[k] for k in sorted(sim_by_key)]
        base_by_key = {f.finding_key: f for f in baseline_findings}
        added = [f for k, f in sim_by_key.items() if k not in base_by_key]
        removed = [f for k, f in base_by_key.items() if k not in sim_by_key]
        worsened: list[OverlayFinding] = []
        improved: list[OverlayFinding] = []
        for key in sorted(set(base_by_key) & set(sim_by_key)):
            b = base_by_key[key]
            s = sim_by_key[key]
            if _SEVERITY_RANK.get(s.severity, 0) > _SEVERITY_RANK.get(b.severity, 0):
                worsened.append(s)
            elif _SEVERITY_RANK.get(s.severity, 0) < _SEVERITY_RANK.get(b.severity, 0):
                improved.append(s)

        overlay_hash = snapshot_hash(
            {
                "version": SCENARIO_GRAPH_OVERLAY_VERSION,
                "assumption_ids": assumption_ids,
                "impacted": sorted(impacted)[:MAX_GRAPH_NODES],
                "added": [f.finding_key for f in added],
                "removed": [f.finding_key for f in removed],
                "ownership_delta": ownership_delta,
                "capability_delta": capability_delta,
                "delay_days": delay_days,
            }
        )

        return GraphOverlayResult(
            nodes_examined=min(len(nodes_by_id), MAX_GRAPH_NODES),
            edges_examined=min(len(list(edges)), MAX_GRAPH_EDGES),
            truncated=truncated,
            baseline_findings=baseline_findings,
            simulated_findings=simulated,
            findings_added=added,
            findings_removed=removed,
            findings_worsened=worsened,
            findings_improved=improved,
            impacted_node_ids=sorted(impacted)[:MAX_GRAPH_NODES],
            impacted_project_ids=sorted(project_ids),
            impacted_initiative_ids=sorted(initiative_ids),
            critical_initiative_ids=sorted(critical_initiative_ids),
            path_explanations=paths[:MAX_RETURNED_PATHS],
            ownership_concentration_delta=ownership_delta,
            capability_concentration_delta=capability_delta,
            dependency_delay_days=delay_days,
            blast_radius_node_count=blast_count,
            assumption_ids=assumption_ids,
            overlay_hash=overlay_hash,
        )
