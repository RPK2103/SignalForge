"""Local connector CLI — no raw tokens as arguments; non-zero exit on failure."""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy.orm import Session

from app.connectors.config import hash_connector_config, validate_connector_config
from app.connectors.credentials import validate_credential_reference
from app.connectors.errors import ConnectorError
from app.connectors.orchestrator import IngestionOrchestrator
from app.connectors.registry import get_default_registry
from app.db.session import get_engine, init_engine
from app.db.unit_of_work import UnitOfWork
from app.domain import enterprise_models as dm
from app.domain.enterprise_enums import DataSourceStatus, DataSourceType, PermissionClassification
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseError


def _session() -> Session:
    init_engine()
    engine = get_engine()
    return Session(engine)


def cmd_list_connectors(_args: argparse.Namespace) -> int:
    registry = get_default_registry()
    for desc in registry.list_descriptors():
        ops = "operational" if desc.capabilities.operational else "staged"
        streams = ",".join(s.name for s in desc.streams)
        print(f"{desc.connector_key}\t{desc.display_name}\t{ops}\tstreams={streams}")
    return 0


def cmd_validate_data_source(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        source = uow.data_sources.get_data_source(ctx, args.data_source_id)
        if source is None:
            print("error: data source not found for tenant", file=sys.stderr)
            return 1
        try:
            if source.credential_reference:
                validate_credential_reference(source.credential_reference)
            if not source.connector_config:
                print("error: missing connector_config", file=sys.stderr)
                return 1
            config = validate_connector_config(source.source_type.value, source.connector_config)
            print(
                json.dumps(
                    {
                        "data_source_id": source.data_source_id,
                        "source_type": source.source_type.value,
                        "config_hash": hash_connector_config(config),
                        "enabled_streams": config.get("enabled_streams"),
                        "credential_reference_present": bool(source.credential_reference),
                    },
                    indent=2,
                )
            )
            return 0
        except ConnectorError as exc:
            print(f"error: {exc.category.value}: {exc.safe_message}", file=sys.stderr)
            return 1


def cmd_sync_data_source(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = IngestionOrchestrator(uow)
            result = orch.sync_data_source(
                ctx,
                args.data_source_id,
                maximum_pages=args.maximum_pages,
                streams=args.streams.split(",") if args.streams else None,
            )
            print(
                json.dumps(
                    {
                        "ingestion_run_id": result.ingestion_run_id,
                        "status": result.status.value,
                        "streams": result.streams,
                        "counts": result.counters.as_dict(),
                        "freshness_state": result.freshness_state.value,
                        "error_summary": result.error_summary,
                    },
                    indent=2,
                )
            )
            return 0 if result.status.value in {"succeeded", "partial"} else 1
        except (ConnectorError, EnterpriseError) as exc:
            msg = getattr(exc, "safe_message", None) or str(exc)
            print(f"error: {msg}", file=sys.stderr)
            return 1


def cmd_inspect_checkpoint(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        page = uow.connector_checkpoints.list_for_source(
            ctx, data_source_id=args.data_source_id, limit=100
        )
        items = [
            {
                "stream_name": c.stream_name,
                "version": c.version,
                "high_watermark_time": c.high_watermark_time.isoformat()
                if c.high_watermark_time
                else None,
                "high_watermark_source_id": c.high_watermark_source_id,
                "cursor_hash": c.cursor_hash,
                "last_successful_run_id": c.last_successful_run_id,
            }
            for c in page.items
        ]
        print(json.dumps({"total": page.total, "checkpoints": items}, indent=2))
        return 0


def cmd_list_dead_letters(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        if args.ingestion_run_id:
            page = uow.ingestion_dead_letters.list_for_run(
                ctx, ingestion_run_id=args.ingestion_run_id, limit=args.limit
            )
        else:
            page = uow.ingestion_dead_letters.list_for_source(
                ctx, data_source_id=args.data_source_id, limit=args.limit
            )
        items = [
            {
                "dead_letter_id": d.dead_letter_id,
                "stream_name": d.stream_name,
                "error_category": d.error_category,
                "replay_state": d.replay_state.value,
                "attempt_count": d.attempt_count,
                "sanitized_error_summary": d.sanitized_error_summary,
            }
            for d in page.items
        ]
        print(json.dumps({"total": page.total, "dead_letters": items}, indent=2))
        return 0


def cmd_replay_dead_letter(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        orch = IngestionOrchestrator(uow)
        result = orch.replay_dead_letter(ctx, args.dead_letter_id)
        print(
            json.dumps(
                {
                    "dead_letter_id": result.dead_letter_id,
                    "replay_state": result.replay_state.value,
                    "attempt_count": result.attempt_count,
                },
                indent=2,
            )
        )
        return 0 if result.replay_state.value == "replayed" else 1


def cmd_register_github_source(args: argparse.Namespace) -> int:
    """Helper for local validation: register a GitHub data source with non-secret config."""
    ctx = TenantContext.require(args.tenant_id)
    config = validate_connector_config(
        "github",
        {
            "owner": args.owner,
            "repository": args.repository,
            "enabled_streams": (
                args.streams.split(",") if args.streams else ["repository", "issues"]
            ),
            "page_size": args.page_size,
            "maximum_pages": args.maximum_pages,
            "overlap_seconds": 60,
        },
    )
    cred_ref = args.credential_reference or "public://none"
    validate_credential_reference(cred_ref)
    with _session() as session:
        uow = UnitOfWork(session)
        source = dm.DataSource(
            data_source_id=build_entity_id(
                "ds",
                ctx.tenant_id,
                "github",
                args.display_name or f"{args.owner}/{args.repository}",
            ),
            tenant_id=ctx.tenant_id,
            source_type=DataSourceType.GITHUB,
            display_name=args.display_name or f"GitHub {args.owner}/{args.repository}",
            credential_reference=cred_ref,
            connector_config=config,
            connector_config_schema_version="1",
            connector_config_hash=hash_connector_config(config),
            status=DataSourceStatus.REGISTERED,
            permission_classification=PermissionClassification.PUBLIC,
        )
        uow.data_sources.add_data_source(ctx, source)
        uow.commit()
        print(json.dumps({"data_source_id": source.data_source_id}, indent=2))
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.connectors.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-connectors")
    p.set_defaults(func=cmd_list_connectors)

    p = sub.add_parser("validate-data-source")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--data-source-id", required=True)
    p.set_defaults(func=cmd_validate_data_source)

    p = sub.add_parser("sync-data-source")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--data-source-id", required=True)
    p.add_argument("--maximum-pages", type=int, default=None)
    p.add_argument("--streams", default=None, help="Comma-separated stream names")
    p.set_defaults(func=cmd_sync_data_source)

    p = sub.add_parser("inspect-checkpoint")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--data-source-id", required=True)
    p.set_defaults(func=cmd_inspect_checkpoint)

    p = sub.add_parser("list-dead-letters")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--data-source-id", required=True)
    p.add_argument("--ingestion-run-id", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_list_dead_letters)

    p = sub.add_parser("replay-dead-letter")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--dead-letter-id", required=True)
    p.set_defaults(func=cmd_replay_dead_letter)

    p = sub.add_parser("register-github-source")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--display-name", default=None)
    p.add_argument("--credential-reference", default="public://none")
    p.add_argument("--streams", default="repository,issues,pull_requests,releases")
    p.add_argument("--page-size", type=int, default=30)
    p.add_argument("--maximum-pages", type=int, default=2)
    p.set_defaults(func=cmd_register_github_source)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
