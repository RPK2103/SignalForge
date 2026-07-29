"""Local Continuous Scenario Intelligence CLI — tenant required; JSON stdout."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import get_engine, init_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.scenario_constants import DEFAULT_HORIZON_DAYS, MIN_WATCH_INTERVAL_MINUTES
from app.domain.scenario_enums import ComparisonDimension, ScenarioKind, ScenarioTargetType
from app.domain.tenant_context import TenantContext
from app.services.enterprise.exceptions import EnterpriseError
from app.services.scenarios.orchestration import ScenarioOrchestrationService
from app.services.scenarios.validation import normalize_assumptions

_SYNTHETIC_BANNER = {
    "data_scope": "synthetic",
    "disclaimer": (
        "SYNTHETIC NovaBank demo scenarios — counterfactual decision support only; "
        "not causal proof; fallback scores are not probabilities."
    ),
}


def _session() -> Session:
    init_engine()
    return Session(get_engine())


def _print(payload: dict | list) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _parse_as_of(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _dump(obj: Any) -> dict | list:
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json")
        # Never dump raw feature vectors.
        if isinstance(data, dict):
            for key in ("simulated_feature_values", "changed_feature_values", "feature_delta"):
                if key in data and isinstance(data[key], dict):
                    data[key] = {
                        "keys": sorted(data[key].keys()),
                        "count": len(data[key]),
                        "omitted": True,
                    }
        return data
    if isinstance(obj, dict):
        return obj
    return {"value": obj}


def _safe_bundle(bundle: Any) -> dict[str, Any]:
    payload = {
        "synthetic": _SYNTHETIC_BANNER,
        "reused_existing": bool(getattr(bundle, "reused_existing", False)),
        "run": _dump(bundle.run),
        "result": _dump(bundle.result) if bundle.result else None,
        "impact_count": len(bundle.impacts or []),
        "impacts": [_dump(i) for i in (bundle.impacts or [])[:50]],
    }
    if bundle.result is not None:
        payload["estimate_label"] = {
            "baseline_estimate_kind": bundle.result.baseline_estimate_kind.value
            if hasattr(bundle.result.baseline_estimate_kind, "value")
            else bundle.result.baseline_estimate_kind,
            "simulated_estimate_kind": bundle.result.simulated_estimate_kind.value
            if hasattr(bundle.result.simulated_estimate_kind, "value")
            else bundle.result.simulated_estimate_kind,
            "note": (
                "uncalibrated_score is a fallback risk score (0-100), not a probability"
                if str(
                    getattr(
                        bundle.result.baseline_estimate_kind,
                        "value",
                        bundle.result.baseline_estimate_kind,
                    )
                )
                == "uncalibrated_score"
                else "calibrated_probability from an active validated model"
            ),
        }
    return payload


def cmd_create(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = ScenarioOrchestrationService(uow)
            definition = orch.create_definition(
                ctx,
                name=args.name,
                description=args.description or "",
                target_type=ScenarioTargetType(args.target_type),
                target_id=args.target_id,
                scenario_kind=ScenarioKind(args.kind),
            )
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "definition": _dump(definition)})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_version(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    assumptions = json.loads(args.assumptions_json)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = ScenarioOrchestrationService(uow)
            version = orch.create_version(
                ctx,
                scenario_definition_id=args.scenario_id,
                assumptions=assumptions,
                created_by_context="cli",
            )
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "version": _dump(version)})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_run(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = ScenarioOrchestrationService(uow)
            bundle = orch.run(
                ctx,
                scenario_version_id=args.version_id,
                as_of_at=_parse_as_of(args.as_of),
                horizon_days=args.horizon_days,
            )
            uow.commit()
            _print(_safe_bundle(bundle))
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_compare(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    run_ids = [x.strip() for x in args.run_ids.split(",") if x.strip()]
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = ScenarioOrchestrationService(uow)
            result = orch.compare(
                ctx,
                run_ids,
                sort_dimension=args.sort_dimension,
                descending=not args.ascending,
            )
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "comparison": _dump(result)})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_list(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        page = uow.scenario_definitions.list(ctx, limit=args.limit, offset=args.offset)
        _print({"synthetic": _SYNTHETIC_BANNER, "page": _dump(page)})
        return 0


def cmd_show(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        definition = uow.scenario_definitions.get(ctx, args.scenario_id)
        if definition is None:
            print("error: Scenario definition not found for this tenant", file=sys.stderr)
            return 1
        versions = uow.scenario_versions.list_for_definition(ctx, args.scenario_id, limit=20)
        _print(
            {
                "synthetic": _SYNTHETIC_BANNER,
                "definition": _dump(definition),
                "versions": _dump(versions),
            }
        )
        return 0


def cmd_list_runs(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        if uow.scenario_definitions.get(ctx, args.scenario_id) is None:
            print("error: Scenario definition not found for this tenant", file=sys.stderr)
            return 1
        page = uow.scenario_runs.list_for_definition(
            ctx, args.scenario_id, limit=args.limit, offset=args.offset
        )
        _print({"synthetic": _SYNTHETIC_BANNER, "page": _dump(page)})
        return 0


def cmd_create_watch(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = ScenarioOrchestrationService(uow)
            watch = orch.create_watch(
                ctx,
                scenario_version_id=args.version_id,
                minimum_interval_minutes=args.minimum_interval_minutes,
            )
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "watch": _dump(watch)})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_pause_watch(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = ScenarioOrchestrationService(uow)
            watch = orch.pause_watch(ctx, args.watch_id)
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "watch": _dump(watch)})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_resume_watch(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = ScenarioOrchestrationService(uow)
            watch = orch.resume_watch(ctx, args.watch_id)
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "watch": _dump(watch)})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_evaluate_watch(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = ScenarioOrchestrationService(uow)
            result = orch.evaluate_watch(
                ctx,
                args.watch_id,
                as_of_at=_parse_as_of(args.as_of),
                horizon_days=args.horizon_days,
                force=args.force,
            )
            uow.commit()
            _print(
                {
                    "synthetic": _SYNTHETIC_BANNER,
                    "action": result.action.value
                    if hasattr(result.action, "value")
                    else result.action,
                    "evaluation": _dump(result),
                }
            )
            return 0 if result.action.value != "failed" else 1
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_evaluate_due(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = ScenarioOrchestrationService(uow)
            summary = orch.evaluate_due(ctx, limit=args.limit, horizon_days=args.horizon_days)
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "summary": _dump(summary)})
            return 0 if summary.failed == 0 else 1
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_list_triggers(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        if uow.scenario_watches.get(ctx, args.watch_id) is None:
            print("error: Scenario watch not found for this tenant", file=sys.stderr)
            return 1
        page = uow.scenario_trigger_events.list_for_watch(
            ctx, args.watch_id, limit=args.limit, offset=args.offset
        )
        _print({"synthetic": _SYNTHETIC_BANNER, "page": _dump(page)})
        return 0


def cmd_validate(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    assumptions = json.loads(args.assumptions_json)
    try:
        normalized = normalize_assumptions(args.kind, assumptions)
        _print(
            {
                "synthetic": _SYNTHETIC_BANNER,
                "tenant_id": ctx.tenant_id,
                "valid": True,
                "normalized": normalized,
            }
        )
        return 0
    except (EnterpriseError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.scenarios")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scenario-create")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--target-type", required=True, choices=[e.value for e in ScenarioTargetType])
    p.add_argument("--target-id", required=True)
    p.add_argument("--kind", required=True, choices=[e.value for e in ScenarioKind])
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("scenario-version")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--scenario-id", required=True)
    p.add_argument("--assumptions-json", required=True)
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("scenario-run")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--version-id", required=True)
    p.add_argument("--as-of", default=None)
    p.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("scenario-compare")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--run-ids", required=True, help="Comma-separated run IDs")
    p.add_argument(
        "--sort-dimension",
        default=ComparisonDimension.AFFECTED_CRITICAL_INITIATIVE_COUNT.value,
    )
    p.add_argument("--ascending", action="store_true")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("scenario-list")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--offset", type=int, default=0)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("scenario-show")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--scenario-id", required=True)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("scenario-list-runs")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--scenario-id", required=True)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--offset", type=int, default=0)
    p.set_defaults(func=cmd_list_runs)

    p = sub.add_parser("scenario-create-watch")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--version-id", required=True)
    p.add_argument(
        "--minimum-interval-minutes",
        type=int,
        default=MIN_WATCH_INTERVAL_MINUTES,
    )
    p.set_defaults(func=cmd_create_watch)

    p = sub.add_parser("scenario-pause-watch")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--watch-id", required=True)
    p.set_defaults(func=cmd_pause_watch)

    p = sub.add_parser("scenario-resume-watch")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--watch-id", required=True)
    p.set_defaults(func=cmd_resume_watch)

    p = sub.add_parser("scenario-evaluate-watch")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--watch-id", required=True)
    p.add_argument("--as-of", default=None)
    p.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_evaluate_watch)

    p = sub.add_parser("scenario-evaluate-due")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.set_defaults(func=cmd_evaluate_due)

    p = sub.add_parser("scenario-list-triggers")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--watch-id", required=True)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--offset", type=int, default=0)
    p.set_defaults(func=cmd_list_triggers)

    p = sub.add_parser("scenario-validate")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--kind", required=True, choices=[e.value for e in ScenarioKind])
    p.add_argument("--assumptions-json", required=True)
    p.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
