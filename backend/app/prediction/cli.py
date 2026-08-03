"""Local Delivery Prediction CLI — tenant required; JSON stdout; synthetic labeled."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import get_engine, init_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.prediction_constants import DEFAULT_HORIZON_DAYS
from app.domain.prediction_enums import PredictionTargetType
from app.domain.prediction_models import PredictionModel
from app.domain.tenant_context import TenantContext
from app.security.context import internal_system_context
from app.services.enterprise.exceptions import EnterpriseError
from app.services.prediction.orchestration import PredictionOrchestrationService

_SYNTHETIC_BANNER = {
    "data_scope": "synthetic",
    "disclaimer": "SYNTHETIC NovaBank demo data — not production, not customer data.",
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


def _model_public(model: PredictionModel) -> dict[str, Any]:
    """Serialize a model without dumping coefficient payloads / binaries."""
    data = model.model_dump(mode="json")
    payload = data.get("parameter_payload") or {}
    data["parameter_payload"] = {
        "keys": sorted(str(k) for k in payload.keys())[:24],
        "feature_count": len(payload.get("feature_list") or []),
        "has_calibrator": bool(
            payload.get("calibrator") or payload.get("platt") or payload.get("calibration")
        ),
        "omitted": True,
        "reason": "model parameter payload omitted from CLI (no binary dump)",
    }
    data["synthetic_note"] = _SYNTHETIC_BANNER["disclaimer"]
    return data


def _dump_model(obj: Any) -> dict | list:
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json")
        if isinstance(data, dict) and "parameter_payload" in data:
            return _model_public(obj)
        return data
    if isinstance(obj, dict):
        return obj
    return {"value": obj}


def cmd_build_dataset(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = PredictionOrchestrationService(uow)
            manifest = orch.build_dataset(ctx, horizon_days=args.horizon_days)
            uow.commit()
            payload = _dump_model(manifest)
            payload["synthetic"] = _SYNTHETIC_BANNER
            _print(payload)
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_train(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = PredictionOrchestrationService(uow)
            model = orch.train(ctx, args.manifest_id, seed=args.seed)
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "model": _model_public(model)})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    # Explicit trusted internal context — still passes AuthorizationService.
    security = internal_system_context(
        args.tenant_id, correlation_id=f"cli_pred_eval_{args.model_id}"
    )
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = PredictionOrchestrationService(uow)
            evaluation = orch.evaluate(
                ctx,
                args.model_id,
                security=security,
                mark_validated_if_passing=True,
            )
            uow.commit()
            payload = _dump_model(evaluation)
            payload["synthetic"] = _SYNTHETIC_BANNER
            _print(payload)
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_promote(args: argparse.Namespace) -> int:
    if not args.confirm:
        print(
            "error: promote requires --confirm (explicit promotion of a validated model)",
            file=sys.stderr,
        )
        return 1
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = PredictionOrchestrationService(uow)
            model = orch.promote(ctx, args.model_id, confirm=True)
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "model": _model_public(model)})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_retire(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = PredictionOrchestrationService(uow)
            model = orch.retire(ctx, args.model_id)
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "model": _model_public(model)})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_predict(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    try:
        target_type = PredictionTargetType(args.target_type)
    except ValueError:
        print(
            "error: --target-type must be 'project' or 'initiative'",
            file=sys.stderr,
        )
        return 1
    as_of = _parse_as_of(args.as_of)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = PredictionOrchestrationService(uow)
            bundle = orch.predict(
                ctx,
                target_type,
                args.target_id,
                as_of_at=as_of,
                horizon_days=args.horizon_days,
            )
            uow.commit()
            payload = _dump_model(bundle)
            payload["synthetic"] = _SYNTHETIC_BANNER
            _print(payload)
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_backtest(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            orch = PredictionOrchestrationService(uow)
            result = orch.backtest(ctx, horizon_days=args.horizon_days)
            uow.commit()
            if isinstance(result, dict):
                result = {**result, "synthetic": _SYNTHETIC_BANNER}
            else:
                result = {"result": result, "synthetic": _SYNTHETIC_BANNER}
            _print(result)
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_list_models(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        models = orch.list_models(ctx, limit=min(args.limit, 100), offset=0)
        _print(
            {
                "synthetic": _SYNTHETIC_BANNER,
                "total": len(models),
                "items": [_model_public(m) for m in models],
            }
        )
        return 0


def cmd_list_evaluations(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        evaluations = orch.list_evaluations(
            ctx, model_id=args.model_id, limit=min(args.limit, 100), offset=0
        )
        _print(
            {
                "synthetic": _SYNTHETIC_BANNER,
                "total": len(evaluations),
                "items": [_dump_model(e) for e in evaluations],
            }
        )
        return 0


def cmd_data_health(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        health = orch.data_health(ctx)
        payload = _dump_model(health)
        payload["synthetic"] = _SYNTHETIC_BANNER
        _print(payload)
        return 0


def cmd_validate(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        orch = PredictionOrchestrationService(uow)
        result = orch.validate_pipeline(ctx)
        result["synthetic"] = _SYNTHETIC_BANNER
        _print(result)
        return 0 if result.get("passed") else 1


def cmd_seed_outcomes(args: argparse.Namespace) -> int:
    """Seed synthetic NovaBank DeliveryOutcome history (idempotent)."""
    if args.tenant_id.strip().lower() != "novabank":
        print(
            "error: seed-outcomes is defined for the NovaBank synthetic tenant only",
            file=sys.stderr,
        )
        return 1
    from app.db.prediction_seed import seed_prediction_history

    with _session() as session:
        try:
            counts = seed_prediction_history(session)
            session.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, "created": counts})
            return 0
        except Exception as exc:  # pragma: no cover - CLI guard
            session.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.prediction",
        description="Delivery Prediction CLI (synthetic demo; no model binary dump)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build-dataset", help="Build temporal dataset manifest")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.set_defaults(func=cmd_build_dataset)

    p = sub.add_parser("train", help="Train candidate model from manifest")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--manifest-id", required=True)
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("evaluate", help="Evaluate a model on the test split")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--model-id", required=True)
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("promote", help="Promote a validated model (requires --confirm)")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--model-id", required=True)
    p.add_argument(
        "--confirm",
        action="store_true",
        help="Required explicit confirmation for promotion",
    )
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("retire", help="Retire a model")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--model-id", required=True)
    p.set_defaults(func=cmd_retire)

    p = sub.add_parser("predict", help="Run delivery prediction for a target")
    p.add_argument("--tenant-id", required=True)
    p.add_argument(
        "--target-type",
        required=True,
        choices=["project", "initiative"],
    )
    p.add_argument("--target-id", required=True)
    p.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--as-of", default=None, help="Optional ISO datetime")
    p.set_defaults(func=cmd_predict)

    p = sub.add_parser("backtest", help="Run temporal backtest harness")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("list-models", help="List prediction models")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_list_models)

    p = sub.add_parser("list-evaluations", help="List model evaluations")
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--model-id", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_list_evaluations)

    p = sub.add_parser("data-health", help="Labeled-data sufficiency health")
    p.add_argument("--tenant-id", required=True)
    p.set_defaults(func=cmd_data_health)

    p = sub.add_parser("validate", help="Validate prediction pipeline wiring")
    p.add_argument("--tenant-id", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser(
        "seed-outcomes",
        help="Seed synthetic NovaBank DeliveryOutcome history (idempotent)",
    )
    p.add_argument("--tenant-id", required=True)
    p.set_defaults(func=cmd_seed_outcomes)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
