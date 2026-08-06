"""CLI for NovaBank realistic enterprise demo tenant."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import get_engine, init_engine
from app.demo.novabank.constants import AS_OF_AT, DATASET_VERSION, TENANT_ID
from app.demo.novabank.service import NovaBankDemoService
from app.security.context import internal_system_context


def _parse_as_of(value: str | None) -> datetime:
    if value is None:
        return AS_OF_AT
    raw = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt != AS_OF_AT:
        raise SystemExit(
            f"--as-of must equal canonical anchor {AS_OF_AT.isoformat()} (or omit the flag)"
        )
    return dt


def _session(database_url: str | None) -> Session:
    if database_url:
        os.environ["DATABASE_URL"] = database_url
    init_engine(database_url)
    return Session(get_engine(database_url))


def _print(payload: Any, *, as_json: bool) -> None:
    if as_json or isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return
    print(payload)


def _security(correlation_id: str):
    return internal_system_context(TENANT_ID, correlation_id=correlation_id)


def cmd_seed(args: argparse.Namespace) -> int:
    _parse_as_of(args.as_of)
    session = _session(args.database_url)
    try:
        service = NovaBankDemoService(session, _security(correlation_id="demo-novabank-seed"))
        result = service.seed()
        if args.json:
            _print(result, as_json=True)
        else:
            print(f"NovaBank seed complete dataset_version={DATASET_VERSION}")
            print(f"  manifest_hash={result['manifest_hash']}")
            print(f"  created_total={result['created_total']}")
            print(f"  duration_ms={result['duration_ms']}")
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_materialize(args: argparse.Namespace) -> int:
    _parse_as_of(args.as_of)
    session = _session(args.database_url)
    try:
        service = NovaBankDemoService(
            session, _security(correlation_id="demo-novabank-materialize")
        )
        result = service.materialize()
        _print(result, as_json=args.json or True)
        return 0 if not result.get("errors") else 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_validate(args: argparse.Namespace) -> int:
    _parse_as_of(args.as_of)
    session = _session(args.database_url)
    try:
        service = NovaBankDemoService(session, _security(correlation_id="demo-novabank-validate"))
        report = service.validate()
        payload = report.to_dict()
        _print(payload, as_json=True)
        return 0 if report.ok else 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_manifest(args: argparse.Namespace) -> int:
    session = _session(args.database_url)
    try:
        service = NovaBankDemoService(session, _security(correlation_id="demo-novabank-manifest"))
        _print(service.manifest(), as_json=True)
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}), file=sys.stderr)
        return 1
    finally:
        session.close()


def cmd_report(args: argparse.Namespace) -> int:
    session = _session(args.database_url)
    try:
        service = NovaBankDemoService(session, _security(correlation_id="demo-novabank-report"))
        _print(service.report(), as_json=True)
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}), file=sys.stderr)
        return 1
    finally:
        session.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.demo")
    sub = parser.add_subparsers(dest="command", required=True)

    novabank = sub.add_parser("novabank", help="NovaBank enterprise demo tenant")
    nsub = novabank.add_subparsers(dest="novabank_command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--database-url", default=None, help="Explicit database URL")
        p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
        p.add_argument(
            "--as-of",
            default=None,
            help="Must equal canonical AS_OF_AT when provided",
        )

    seed_p = nsub.add_parser("seed", help="Seed canonical NovaBank Prompt 9 dataset")
    add_common(seed_p)
    seed_p.set_defaults(func=cmd_seed)

    mat_p = nsub.add_parser("materialize", help="Materialize graph/scenarios/briefs")
    add_common(mat_p)
    mat_p.set_defaults(func=cmd_materialize)

    val_p = nsub.add_parser("validate", help="Validate inventory and story coverage")
    add_common(val_p)
    val_p.set_defaults(func=cmd_validate)

    man_p = nsub.add_parser("manifest", help="Print dataset manifest")
    add_common(man_p)
    man_p.set_defaults(func=cmd_manifest)

    rep_p = nsub.add_parser("report", help="Validation + story report")
    add_common(rep_p)
    rep_p.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
