"""Deterministic Delivery Graph analysis and finding reconciliation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import enterprise as ent_orm
from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.graph_enums import (
    GRAPH_ANALYSIS_VERSION,
    GRAPH_PROJECTION_VERSION,
    GraphAnalysisRunState,
    GraphDataQualityWarning,
    GraphEdgeOrigin,
    GraphEdgeType,
    GraphFindingSeverity,
    GraphFindingStatus,
    GraphFindingType,
    GraphNodeType,
)
from app.domain.graph_models import (
    GraphAnalysisRun,
    GraphFinding,
    GraphFindingEvidence,
)
from app.domain.tenant_context import TenantContext
from app.services.graph.confidence import finding_confidence
from app.services.graph.projection_service import graph_node_id
from app.services.graph.query_service import DeliveryGraphQueryService
from app.services.persistence.snapshot_service import snapshot_hash

logger = logging.getLogger("signalforge.graph.analysis")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def analysis_run_id(tenant_id: str, started_at: datetime) -> str:
    return build_entity_id("garun", tenant_id, started_at.isoformat())


def finding_id(tenant_id: str, finding_hash: str) -> str:
    return build_entity_id("gfind", tenant_id, finding_hash[:32])


class GraphAnalysisService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._query = DeliveryGraphQueryService(uow)

    def analyze(self, ctx: TenantContext) -> GraphAnalysisRun:
        started = _utcnow()
        run = GraphAnalysisRun(
            tenant_id=ctx.tenant_id,
            graph_analysis_run_id=analysis_run_id(ctx.tenant_id, started),
            analysis_version=GRAPH_ANALYSIS_VERSION,
            graph_projection_version=GRAPH_PROJECTION_VERSION,
            state=GraphAnalysisRunState.RUNNING,
            started_at=started,
        )
        self._uow.graph_analysis_runs.add_run(ctx, run)
        self._uow.session.flush()
        logger.info(
            "graph.analysis.started tenant_id=%s run_id=%s",
            ctx.tenant_id,
            run.graph_analysis_run_id,
        )

        try:
            observed_hashes: set[str] = set()
            created = observed = 0

            for finding in self._detect_all(ctx, started):
                observed_hashes.add(finding.finding_hash)
                saved, action = self._uow.graph_findings.upsert_active_finding(ctx, finding)
                if action == "created":
                    created += 1
                    logger.info(
                        "graph.finding.created tenant_id=%s finding_id=%s type=%s",
                        ctx.tenant_id,
                        saved.graph_finding_id,
                        saved.finding_type.value,
                    )
                    for edge_id in saved.supporting_edge_ids[:50]:
                        self._uow.graph_findings.add_evidence(
                            ctx,
                            GraphFindingEvidence(
                                tenant_id=ctx.tenant_id,
                                graph_finding_evidence_id=build_entity_id(
                                    "gfev", ctx.tenant_id, saved.graph_finding_id, "edge", edge_id
                                ),
                                graph_finding_id=saved.graph_finding_id,
                                evidence_kind="edge",
                                evidence_ref_id=edge_id,
                            ),
                        )
                    for ev_id in saved.supporting_evidence_signal_ids[:50]:
                        self._uow.graph_findings.add_evidence(
                            ctx,
                            GraphFindingEvidence(
                                tenant_id=ctx.tenant_id,
                                graph_finding_evidence_id=build_entity_id(
                                    "gfev",
                                    ctx.tenant_id,
                                    saved.graph_finding_id,
                                    "signal",
                                    ev_id,
                                ),
                                graph_finding_id=saved.graph_finding_id,
                                evidence_kind="evidence_signal",
                                evidence_ref_id=ev_id,
                            ),
                        )
                else:
                    observed += 1
                    logger.info(
                        "graph.finding.observed tenant_id=%s finding_id=%s type=%s",
                        ctx.tenant_id,
                        saved.graph_finding_id,
                        saved.finding_type.value,
                    )

            # Resolve findings no longer present.
            resolved = 0
            active = self._uow.graph_findings.list_active_hashes(ctx)
            for fhash, fid in active.items():
                if fhash not in observed_hashes:
                    self._uow.graph_findings.resolve_finding(ctx, fid, started)
                    resolved += 1
                    logger.info(
                        "graph.finding.resolved tenant_id=%s finding_id=%s",
                        ctx.tenant_id,
                        fid,
                    )

            run.findings_created = created
            run.findings_observed = observed
            run.findings_resolved = resolved
            run.state = GraphAnalysisRunState.SUCCEEDED
            run.completed_at = _utcnow()
            self._uow.graph_analysis_runs.update_run(ctx, run)
            self._uow.session.flush()
            logger.info(
                "graph.analysis.completed tenant_id=%s run_id=%s created=%s "
                "observed=%s resolved=%s",
                ctx.tenant_id,
                run.graph_analysis_run_id,
                created,
                observed,
                resolved,
            )
            return run
        except Exception as exc:
            self._uow.session.rollback()
            logger.info(
                "graph.analysis.failed tenant_id=%s error_type=%s",
                ctx.tenant_id,
                type(exc).__name__,
            )
            raise

    def _detect_all(self, ctx: TenantContext, now: datetime) -> list[GraphFinding]:
        findings: list[GraphFinding] = []
        findings.extend(self._repo_ownership_concentration(ctx, now))
        findings.extend(self._capability_ownership_concentration(ctx, now))
        findings.extend(self._single_person_dependency(ctx, now))
        findings.extend(self._cross_team_dependencies(ctx, now))
        findings.extend(self._derived_unmodeled_dependencies(ctx, now))
        findings.extend(self._dependency_cycles(ctx, now))
        findings.extend(self._availability_blast_radius(ctx, now))
        findings.extend(self._knowledge_concentration(ctx, now))
        findings.sort(key=lambda f: (f.finding_type.value, f.finding_hash))
        return findings

    def _make_finding(
        self,
        ctx: TenantContext,
        *,
        finding_type: GraphFindingType,
        severity: GraphFindingSeverity,
        title: str,
        explanation: str,
        primary_node_id: str,
        affected_node_ids: list[str],
        supporting_edge_ids: list[str],
        supporting_evidence_signal_ids: list[str],
        rule_id: str,
        now: datetime,
        warnings: list[GraphDataQualityWarning] | None = None,
        is_derived: bool = False,
        has_missing_owner: bool = False,
        has_availability_overlap: bool = False,
    ) -> GraphFinding:
        hash_payload = {
            "finding_type": finding_type.value,
            "primary_node_id": primary_node_id,
            "affected_node_ids": sorted(affected_node_ids),
            "rule_id": rule_id,
            "rule_version": "1",
        }
        fhash = snapshot_hash(hash_payload)
        conf, conf_warnings = finding_confidence(
            evidence_count=len(supporting_edge_ids) + len(supporting_evidence_signal_ids),
            has_missing_owner=has_missing_owner,
            is_derived=is_derived,
            has_availability_overlap=has_availability_overlap,
        )
        all_warnings = list(warnings or []) + conf_warnings
        # Dedupe warnings preserving order
        seen: set[str] = set()
        deduped: list[GraphDataQualityWarning] = []
        for w in all_warnings:
            if w.value not in seen:
                seen.add(w.value)
                deduped.append(w)
        return GraphFinding(
            tenant_id=ctx.tenant_id,
            graph_finding_id=finding_id(ctx.tenant_id, fhash),
            finding_type=finding_type,
            status=GraphFindingStatus.ACTIVE,
            severity=severity,
            confidence=conf,
            title=title[:256],
            explanation=explanation[:2048],
            primary_node_id=primary_node_id,
            affected_node_ids=sorted(set(affected_node_ids))[:200],
            supporting_edge_ids=sorted(set(supporting_edge_ids))[:100],
            supporting_evidence_signal_ids=sorted(set(supporting_evidence_signal_ids))[:100],
            data_quality_warnings=deduped,
            rule_id=rule_id,
            rule_version="1",
            detected_at=now,
            last_observed_at=now,
            finding_hash=fhash,
        )

    def _iter_nodes(self, ctx: TenantContext, node_type: GraphNodeType):
        offset = 0
        while True:
            page = self._uow.graph_nodes.list_nodes(
                ctx, node_type=node_type, limit=100, offset=offset
            )
            yield from page.items
            if offset + 100 >= page.total:
                break
            offset += 100

    def _repo_ownership_concentration(
        self, ctx: TenantContext, now: datetime
    ) -> list[GraphFinding]:
        findings = []
        for node in self._iter_nodes(ctx, GraphNodeType.REPOSITORY):
            result = self._query.ownership_concentration(ctx, node.graph_node_id)
            if result.single_owner or result.low_redundancy:
                findings.append(
                    self._make_finding(
                        ctx,
                        finding_type=GraphFindingType.REPOSITORY_OWNERSHIP_CONCENTRATION,
                        severity=(
                            GraphFindingSeverity.HIGH
                            if result.single_owner
                            else GraphFindingSeverity.MEDIUM
                        ),
                        title=f"Repository ownership concentration: {node.display_label}",
                        explanation=(
                            f"Rule repo_ownership_concentration_v1: repository "
                            f"'{node.display_label}' has {result.active_owner_count} "
                            f"primary owner(s) and {result.active_contributor_count} "
                            f"contributor(s). concentration_score="
                            f"{result.concentration_score:.2f} (rule-based, not calibrated). "
                            f"single_owner={result.single_owner}."
                        ),
                        primary_node_id=node.graph_node_id,
                        affected_node_ids=result.primary_owner_node_ids,
                        supporting_edge_ids=result.supporting_edge_ids,
                        supporting_evidence_signal_ids=result.supporting_evidence_signal_ids,
                        rule_id="repo_ownership_concentration_v1",
                        now=now,
                        warnings=result.data_quality_warnings,
                        has_missing_owner=bool(result.data_quality_warnings),
                    )
                )
        return findings

    def _capability_ownership_concentration(
        self, ctx: TenantContext, now: datetime
    ) -> list[GraphFinding]:
        findings = []
        for node in self._iter_nodes(ctx, GraphNodeType.CAPABILITY):
            # Ownership concentration for capabilities uses OWNS edges only so
            # catalog contributes_to evidence does not dilute primary ownership.
            neighbors = self._query.neighbors(
                ctx,
                node.graph_node_id,
                direction="incoming",
                edge_types=[GraphEdgeType.OWNS],
                limit=100,
            )
            owners = sorted({nb.node.graph_node_id for nb in neighbors})
            edge_ids = [nb.edge.graph_edge_id for nb in neighbors]
            if 0 < len(owners) <= 2:
                findings.append(
                    self._make_finding(
                        ctx,
                        finding_type=GraphFindingType.CAPABILITY_OWNERSHIP_CONCENTRATION,
                        severity=GraphFindingSeverity.HIGH
                        if len(owners) == 1
                        else GraphFindingSeverity.MEDIUM,
                        title=f"Capability ownership concentration: {node.display_label}",
                        explanation=(
                            f"Rule capability_ownership_concentration_v1: capability "
                            f"'{node.display_label}' has {len(owners)} active primary "
                            f"owner(s) via OWNS edges. Decision-support signal only — "
                            f"not an employee performance ranking."
                        ),
                        primary_node_id=node.graph_node_id,
                        affected_node_ids=owners,
                        supporting_edge_ids=edge_ids,
                        supporting_evidence_signal_ids=[],
                        rule_id="capability_ownership_concentration_v1",
                        now=now,
                        has_missing_owner=len(owners) == 0,
                    )
                )
        return findings

    def _single_person_dependency(self, ctx: TenantContext, now: datetime) -> list[GraphFinding]:
        findings = []
        # Critical initiatives: projects/repos with single engineer owner.
        for init_node in self._iter_nodes(ctx, GraphNodeType.INITIATIVE):
            init = self._uow.session.scalar(
                select(ent_orm.Initiative).where(
                    ent_orm.Initiative.tenant_id == ctx.tenant_id,
                    ent_orm.Initiative.initiative_id == init_node.entity_id,
                )
            )
            if init is None or init.criticality not in {"critical", "high"}:
                continue
            # Reach engineers via supports/owns/contributes paths (bounded).
            neighbors = self._query.neighbors(
                ctx,
                init_node.graph_node_id,
                direction="incoming",
                edge_types=[
                    GraphEdgeType.SUPPORTS,
                    GraphEdgeType.CONTRIBUTES_TO,
                    GraphEdgeType.OWNS,
                ],
                limit=100,
            )
            engineer_ids: set[str] = set()
            edge_ids: list[str] = []
            for nb in neighbors:
                if nb.node.node_type == GraphNodeType.ENGINEER:
                    engineer_ids.add(nb.node.graph_node_id)
                    edge_ids.append(nb.edge.graph_edge_id)
                elif nb.node.node_type == GraphNodeType.TEAM:
                    # Look one hop to engineers.
                    team_nbs = self._query.neighbors(
                        ctx,
                        nb.node.graph_node_id,
                        direction="incoming",
                        edge_types=[GraphEdgeType.MEMBER_OF],
                        node_types=[GraphNodeType.ENGINEER],
                        limit=100,
                    )
                    for tn in team_nbs:
                        engineer_ids.add(tn.node.graph_node_id)
                        edge_ids.append(tn.edge.graph_edge_id)
                    edge_ids.append(nb.edge.graph_edge_id)

            # Also inspect repositories supporting the initiative with single owner.
            for repo in self._iter_nodes(ctx, GraphNodeType.REPOSITORY):
                conc = self._query.ownership_concentration(ctx, repo.graph_node_id)
                if not conc.single_owner:
                    continue
                # Check if repo supports a project under this initiative.
                repo_out = self._query.neighbors(
                    ctx,
                    repo.graph_node_id,
                    direction="outgoing",
                    edge_types=[GraphEdgeType.SUPPORTS, GraphEdgeType.DEPENDS_ON],
                    node_types=[GraphNodeType.PROJECT],
                    limit=50,
                )
                for rn in repo_out:
                    proj = self._uow.session.scalar(
                        select(ent_orm.EnterpriseProject).where(
                            ent_orm.EnterpriseProject.tenant_id == ctx.tenant_id,
                            ent_orm.EnterpriseProject.enterprise_project_id == rn.node.entity_id,
                        )
                    )
                    if proj and proj.initiative_id == init.initiative_id:
                        for owner_id in conc.primary_owner_node_ids:
                            owner = self._uow.graph_nodes.get_node(ctx, owner_id)
                            if owner and owner.node_type == GraphNodeType.ENGINEER:
                                engineer_ids.add(owner_id)
                        edge_ids.extend(conc.supporting_edge_ids)
                        edge_ids.append(rn.edge.graph_edge_id)

            if len(engineer_ids) == 1:
                eng_id = next(iter(engineer_ids))
                findings.append(
                    self._make_finding(
                        ctx,
                        finding_type=GraphFindingType.SINGLE_PERSON_DEPENDENCY,
                        severity=GraphFindingSeverity.CRITICAL
                        if init.criticality == "critical"
                        else GraphFindingSeverity.HIGH,
                        title=f"Single-person dependency on initiative {init_node.display_label}",
                        explanation=(
                            f"Rule single_person_dependency_v1: critical/high initiative "
                            f"'{init_node.display_label}' depends on exactly one active "
                            f"engineer node. This is an evidence-backed decision-support "
                            f"signal, not an employee performance score."
                        ),
                        primary_node_id=init_node.graph_node_id,
                        affected_node_ids=[eng_id],
                        supporting_edge_ids=edge_ids,
                        supporting_evidence_signal_ids=[],
                        rule_id="single_person_dependency_v1",
                        now=now,
                    )
                )
        return findings

    def _cross_team_dependencies(self, ctx: TenantContext, now: datetime) -> list[GraphFinding]:
        findings = []
        # Explicit dependency edges whose source/target teams differ.
        edges = self._uow.graph_edges.list_active_edges_for_traversal(
            ctx,
            edge_types=[
                GraphEdgeType.DEPENDS_ON,
                GraphEdgeType.BLOCKS,
                GraphEdgeType.REQUIRES,
            ],
            max_edges=5000,
        )
        for edge in edges:
            if edge.edge_origin == GraphEdgeOrigin.DERIVED:
                continue
            src = self._uow.graph_nodes.get_node(ctx, edge.source_node_id)
            tgt = self._uow.graph_nodes.get_node(ctx, edge.target_node_id)
            if src is None or tgt is None:
                continue
            src_team = self._team_for_node(ctx, src)
            tgt_team = self._team_for_node(ctx, tgt)
            if src_team and tgt_team and src_team != tgt_team:
                findings.append(
                    self._make_finding(
                        ctx,
                        finding_type=GraphFindingType.CROSS_TEAM_DEPENDENCY,
                        severity=GraphFindingSeverity.MEDIUM,
                        title=(f"Cross-team dependency: {src.display_label} → {tgt.display_label}"),
                        explanation=(
                            f"Rule cross_team_dependency_v1: explicit "
                            f"{edge.edge_type.value} edge crosses team boundary "
                            f"({src_team} → {tgt_team}). Provenance "
                            f"edge_id={edge.graph_edge_id}, "
                            f"origin={edge.edge_origin.value}."
                        ),
                        primary_node_id=edge.source_node_id,
                        affected_node_ids=[edge.target_node_id, src_team, tgt_team],
                        supporting_edge_ids=[edge.graph_edge_id],
                        supporting_evidence_signal_ids=(
                            [edge.supporting_evidence_signal_id]
                            if edge.supporting_evidence_signal_id
                            else []
                        ),
                        rule_id="cross_team_dependency_v1",
                        now=now,
                    )
                )
        return findings

    def _derived_unmodeled_dependencies(
        self, ctx: TenantContext, now: datetime
    ) -> list[GraphFinding]:
        findings = []
        edges = self._uow.graph_edges.list_active_edges_for_traversal(
            ctx,
            edge_types=[
                GraphEdgeType.DEPENDS_ON,
                GraphEdgeType.SUPPORTS,
                GraphEdgeType.BLOCKS,
            ],
            max_edges=5000,
        )
        # Build set of explicit dependency pairs from Manual/Catalog dependency edges.
        explicit_pairs: set[tuple[str, str]] = set()
        for edge in edges:
            if edge.edge_origin in {GraphEdgeOrigin.MANUAL, GraphEdgeOrigin.CATALOG}:
                if edge.supporting_dependency_id or edge.edge_origin == GraphEdgeOrigin.MANUAL:
                    explicit_pairs.add((edge.source_node_id, edge.target_node_id))

        for edge in edges:
            if edge.edge_origin != GraphEdgeOrigin.DERIVED:
                continue
            if (edge.source_node_id, edge.target_node_id) in explicit_pairs:
                continue  # suppressed by explicit record
            if edge.edge_type not in {
                GraphEdgeType.DEPENDS_ON,
                GraphEdgeType.SUPPORTS,
                GraphEdgeType.BLOCKS,
            }:
                continue
            # Only flag derived cross-team supports/depends as unmodeled.
            src = self._uow.graph_nodes.get_node(ctx, edge.source_node_id)
            tgt = self._uow.graph_nodes.get_node(ctx, edge.target_node_id)
            if src is None or tgt is None:
                continue
            src_team = self._team_for_node(ctx, src)
            tgt_team = self._team_for_node(ctx, tgt)
            if not (src_team and tgt_team and src_team != tgt_team):
                continue
            findings.append(
                self._make_finding(
                    ctx,
                    finding_type=GraphFindingType.DERIVED_UNMODELED_DEPENDENCY,
                    severity=GraphFindingSeverity.LOW,
                    title=(
                        f"Derived unmodeled dependency: {src.display_label} → {tgt.display_label}"
                    ),
                    explanation=(
                        f"Rule derived_unmodeled_dependency_v1: derived edge "
                        f"(rule={edge.derivation_rule}) crosses teams with no corresponding "
                        f"active explicit dependency record. Marked derived with bounded "
                        f"confidence; not a confirmed manual fact."
                    ),
                    primary_node_id=edge.source_node_id,
                    affected_node_ids=[edge.target_node_id],
                    supporting_edge_ids=[edge.graph_edge_id],
                    supporting_evidence_signal_ids=[],
                    rule_id="derived_unmodeled_dependency_v1",
                    now=now,
                    is_derived=True,
                    warnings=[GraphDataQualityWarning.NO_EXPLICIT_DEPENDENCY_RECORD],
                )
            )
        return findings

    def _dependency_cycles(self, ctx: TenantContext, now: datetime) -> list[GraphFinding]:
        findings = []
        cycles = self._query.dependency_cycles(ctx)
        for cycle in cycles:
            findings.append(
                self._make_finding(
                    ctx,
                    finding_type=GraphFindingType.DEPENDENCY_CYCLE,
                    severity=GraphFindingSeverity.HIGH,
                    title=f"Dependency cycle: {cycle.canonical_key[:120]}",
                    explanation=(
                        f"Rule dependency_cycle_v1: directed cycle detected among "
                        f"depends_on/blocks/requires edges. Canonical representation: "
                        f"{cycle.canonical_key}. Cycle length={len(cycle.node_ids)}."
                    ),
                    primary_node_id=cycle.node_ids[0] if cycle.node_ids else "unknown",
                    affected_node_ids=cycle.node_ids,
                    supporting_edge_ids=cycle.edge_ids,
                    supporting_evidence_signal_ids=[],
                    rule_id="dependency_cycle_v1",
                    now=now,
                )
            )
        return findings

    def _availability_blast_radius(self, ctx: TenantContext, now: datetime) -> list[GraphFinding]:
        findings = []
        avails = self._uow.session.scalars(
            select(ent_orm.Availability).where(
                ent_orm.Availability.tenant_id == ctx.tenant_id,
                ent_orm.Availability.start_time <= now,
                ent_orm.Availability.end_time > now,
            )
        ).all()
        for avail in avails:
            if avail.target_type != "engineer_profile":
                continue
            if avail.availability_percentage is not None and avail.availability_percentage >= 80:
                continue
            eng_node_id = graph_node_id(ctx.tenant_id, GraphNodeType.ENGINEER, avail.target_id)
            eng_node = self._uow.graph_nodes.get_node(ctx, eng_node_id)
            if eng_node is None:
                continue
            blast = self._query.blast_radius(ctx, eng_node_id, max_depth=4)
            if not blast.affected_initiative_ids and not blast.directly_affected_node_ids:
                continue
            findings.append(
                self._make_finding(
                    ctx,
                    finding_type=GraphFindingType.AVAILABILITY_BLAST_RADIUS,
                    severity=GraphFindingSeverity.HIGH
                    if blast.affected_critical_initiative_ids
                    else GraphFindingSeverity.MEDIUM,
                    title=f"Availability blast radius: {eng_node.display_label}",
                    explanation=(
                        f"Rule availability_blast_radius_v1: engineer '{eng_node.display_label}' "
                        f"has availability_percentage={avail.availability_percentage} overlapping "
                        f"now. Directly affected={len(blast.directly_affected_node_ids)}, "
                        f"initiatives={len(blast.affected_initiative_ids)}, "
                        f"critical_initiatives={len(blast.affected_critical_initiative_ids)}. "
                        f"No delivery-likelihood score is computed."
                    ),
                    primary_node_id=eng_node_id,
                    affected_node_ids=(
                        blast.directly_affected_node_ids + blast.affected_initiative_ids
                    )[:200],
                    supporting_edge_ids=blast.traversed_edge_ids[:100],
                    supporting_evidence_signal_ids=blast.supporting_evidence_signal_ids,
                    rule_id="availability_blast_radius_v1",
                    now=now,
                    has_availability_overlap=True,
                )
            )
        return findings

    def _knowledge_concentration(self, ctx: TenantContext, now: datetime) -> list[GraphFinding]:
        """Knowledge concentration = engineer who is sole owner of capability AND repository."""
        findings = []
        for eng in self._iter_nodes(ctx, GraphNodeType.ENGINEER):
            out = self._query.neighbors(
                ctx,
                eng.graph_node_id,
                direction="outgoing",
                edge_types=[GraphEdgeType.OWNS, GraphEdgeType.CONTRIBUTES_TO],
                limit=100,
            )
            sole_repos = []
            sole_caps = []
            edge_ids = []
            for nb in out:
                if nb.node.node_type == GraphNodeType.REPOSITORY:
                    conc = self._query.ownership_concentration(ctx, nb.node.graph_node_id)
                    if conc.single_owner and eng.graph_node_id in conc.primary_owner_node_ids:
                        sole_repos.append(nb.node.graph_node_id)
                        edge_ids.extend(conc.supporting_edge_ids)
                if (
                    nb.node.node_type == GraphNodeType.CAPABILITY
                    and nb.edge.edge_type == GraphEdgeType.OWNS
                ):
                    # OWNS-only so catalog contributes_to evidence does not dilute.
                    owners = self._query.neighbors(
                        ctx,
                        nb.node.graph_node_id,
                        direction="incoming",
                        edge_types=[GraphEdgeType.OWNS],
                        limit=20,
                    )
                    owner_ids = {o.node.graph_node_id for o in owners}
                    if owner_ids == {eng.graph_node_id}:
                        sole_caps.append(nb.node.graph_node_id)
                        edge_ids.extend([o.edge.graph_edge_id for o in owners])
            if sole_repos and sole_caps:
                findings.append(
                    self._make_finding(
                        ctx,
                        finding_type=GraphFindingType.KNOWLEDGE_CONCENTRATION,
                        severity=GraphFindingSeverity.HIGH,
                        title=f"Knowledge concentration: {eng.display_label}",
                        explanation=(
                            f"Rule knowledge_concentration_v1: engineer '{eng.display_label}' "
                            f"is the sole/low-redundancy owner of {len(sole_repos)} repository "
                            f"node(s) and {len(sole_caps)} capability node(s). This measures "
                            f"knowledge concentration for delivery risk — not employee ranking."
                        ),
                        primary_node_id=eng.graph_node_id,
                        affected_node_ids=sole_repos + sole_caps,
                        supporting_edge_ids=edge_ids,
                        supporting_evidence_signal_ids=[],
                        rule_id="knowledge_concentration_v1",
                        now=now,
                    )
                )
        return findings

    def _team_for_node(self, ctx: TenantContext, node) -> str | None:
        if node.node_type == GraphNodeType.TEAM:
            return node.graph_node_id
        if node.node_type == GraphNodeType.ENGINEER:
            nbs = self._query.neighbors(
                ctx,
                node.graph_node_id,
                direction="outgoing",
                edge_types=[GraphEdgeType.MEMBER_OF],
                node_types=[GraphNodeType.TEAM],
                limit=5,
            )
            return nbs[0].node.graph_node_id if nbs else None
        if node.node_type == GraphNodeType.PROJECT:
            nbs = self._query.neighbors(
                ctx,
                node.graph_node_id,
                direction="incoming",
                edge_types=[GraphEdgeType.OWNS],
                node_types=[GraphNodeType.TEAM],
                limit=5,
            )
            return nbs[0].node.graph_node_id if nbs else None
        if node.node_type == GraphNodeType.REPOSITORY:
            nbs = self._query.neighbors(
                ctx,
                node.graph_node_id,
                direction="incoming",
                edge_types=[GraphEdgeType.OWNS],
                node_types=[GraphNodeType.TEAM],
                limit=5,
            )
            return nbs[0].node.graph_node_id if nbs else None
        return None
