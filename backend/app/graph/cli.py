"""Local Delivery Graph CLI — tenant required; no credentials; bounded output."""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy.orm import Session

from app.db.session import get_engine, init_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseError
from app.services.graph.analysis_service import GraphAnalysisService
from app.services.graph.projection_service import GraphProjectionService
from app.services.graph.query_service import DeliveryGraphQueryService


def _session() -> Session:
    init_engine()
    return Session(get_engine())


def _print(payload: dict | list) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def cmd_rebuild(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            run = GraphProjectionService(uow).full_rebuild(ctx)
            uow.commit()
            _print(
                {
                    "graph_projection_run_id": run.graph_projection_run_id,
                    "state": run.state.value,
                    "nodes_created": run.nodes_created,
                    "nodes_updated": run.nodes_updated,
                    "edges_created": run.edges_created,
                    "edges_updated": run.edges_updated,
                    "edges_closed": run.edges_closed,
                }
            )
            return 0 if run.state.value in {"succeeded", "partial"} else 1
        except EnterpriseError as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_refresh_subject(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    subjects = [s.strip() for s in args.subject_ids.split(",") if s.strip()]
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            run = GraphProjectionService(uow).subject_refresh(ctx, subjects)
            uow.commit()
            _print(
                {
                    "graph_projection_run_id": run.graph_projection_run_id,
                    "state": run.state.value,
                    "subject_ids": run.subject_ids,
                    "nodes_created": run.nodes_created,
                    "edges_created": run.edges_created,
                }
            )
            return 0 if run.state.value in {"succeeded", "partial"} else 1
        except EnterpriseError as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_summary(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        summary = DeliveryGraphQueryService(uow).summary(ctx)
        _print(summary.model_dump(mode="json"))
        return 0


def cmd_path(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            paths = DeliveryGraphQueryService(uow).shortest_paths(
                ctx,
                args.source_node_id,
                args.target_node_id,
                max_depth=args.max_depth,
            )
            _print([p.model_dump(mode="json") for p in paths])
            return 0
        except EnterpriseError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_blast_radius(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            result = DeliveryGraphQueryService(uow).blast_radius(
                ctx, args.origin_node_id, max_depth=args.max_depth
            )
            _print(result.model_dump(mode="json"))
            return 0
        except EnterpriseError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_analyze(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            run = GraphAnalysisService(uow).analyze(ctx)
            uow.commit()
            _print(
                {
                    "graph_analysis_run_id": run.graph_analysis_run_id,
                    "state": run.state.value,
                    "findings_created": run.findings_created,
                    "findings_observed": run.findings_observed,
                    "findings_resolved": run.findings_resolved,
                }
            )
            return 0 if run.state.value == "succeeded" else 1
        except EnterpriseError as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_list_findings(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        page = uow.graph_findings.list_findings(ctx, limit=min(args.limit, 100), offset=0)
        _print(
            {
                "total": page.total,
                "items": [
                    {
                        "graph_finding_id": f.graph_finding_id,
                        "finding_type": f.finding_type.value,
                        "severity": f.severity.value,
                        "confidence": f.confidence,
                        "title": f.title,
                        "rule_id": f.rule_id,
                    }
                    for f in page.items
                ],
            }
        )
        return 0


def cmd_validate(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        summary = DeliveryGraphQueryService(uow).summary(ctx)
        cycles = DeliveryGraphQueryService(uow).dependency_cycles(ctx)
        ok = summary.node_count > 0 and summary.edge_count > 0
        _print(
            {
                "valid": ok,
                "node_count": summary.node_count,
                "edge_count": summary.edge_count,
                "active_finding_count": summary.active_finding_count,
                "cycle_count": len(cycles),
            }
        )
        return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.graph", description="Delivery Graph CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("graph-rebuild", help="Full tenant graph rebuild")
    p.add_argument("--tenant-id", required=True)
    p.set_defaults(func=cmd_rebuild)

    p = sub.add_parser("graph-refresh-subject", help="Subject-level refresh")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--subject-ids", required=True, help="Comma-separated entity IDs (max 50)")
    p.set_defaults(func=cmd_refresh_subject)

    p = sub.add_parser("graph-summary", help="Graph summary")
    p.add_argument("--tenant-id", required=True)
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("graph-path", help="Shortest path")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--source-node-id", required=True)
    p.add_argument("--target-node-id", required=True)
    p.add_argument("--max-depth", type=int, default=6)
    p.set_defaults(func=cmd_path)

    p = sub.add_parser("graph-blast-radius", help="Blast radius")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--origin-node-id", required=True)
    p.add_argument("--max-depth", type=int, default=6)
    p.set_defaults(func=cmd_blast_radius)

    p = sub.add_parser("graph-analyze", help="Run graph analysis")
    p.add_argument("--tenant-id", required=True)
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("graph-list-findings", help="List active findings")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_list_findings)

    p = sub.add_parser("graph-validate", help="Validate projected graph")
    p.add_argument("--tenant-id", required=True)
    p.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
