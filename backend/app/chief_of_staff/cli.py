"""Local AI Chief of Staff CLI — tenant required; JSON stdout."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import get_engine, init_engine
from app.db.unit_of_work import UnitOfWork
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffReviewState,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import ChiefOfStaffRequest
from app.domain.tenant_context import TenantContext
from app.services.chief_of_staff.service import ChiefOfStaffService
from app.services.enterprise.exceptions import EnterpriseError

_SYNTHETIC_BANNER = {
    "data_scope": "synthetic",
    "disclaimer": (
        "SYNTHETIC NovaBank / demo Chief of Staff briefs — decision support only; "
        "not autonomous; uncalibrated scores are not probabilities; "
        "tenant header is not authentication."
    ),
}


def _session() -> Session:
    init_engine()
    return Session(get_engine())


def _print(payload: dict | list) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _parse_as_of(value: str) -> datetime:
    raw = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _dump(obj: Any) -> dict | list:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return obj
    return {"value": obj}


def _safe_outcome(outcome: Any) -> dict[str, Any]:
    run = outcome.run
    brief = outcome.brief
    package = outcome.package
    return {
        "synthetic": _SYNTHETIC_BANNER,
        "run_id": run.run_id,
        "brief_id": brief.brief_id if brief else None,
        "requested_provider": run.requested_provider,
        "final_provider": run.final_provider,
        "generation_state": run.generation_state,
        "failure_category": run.failure_category,
        "evidence_hash": run.evidence_package_hash,
        "output_hash": run.output_hash,
        "grounding_status": run.grounding_result,
        "citation_status": run.citation_result,
        "estimate_kind": brief.estimate_kind if brief else None,
        "probability": brief.probability if brief else None,
        "fallback_visible": (
            outcome.structured_brief.fallback_visible if outcome.structured_brief else None
        ),
        "intent": package.intent.value,
        "target_type": package.target_type.value,
        "target_id": package.target_id,
        "as_of_at": package.as_of_at.isoformat(),
        "truncation": package.truncation.any_truncated,
        # Never print secrets or full provider payloads.
    }


def cmd_generate(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    scenario_ids = [s.strip() for s in (args.scenario_run_ids or "").split(",") if s.strip()]
    sections = [s.strip() for s in (args.sections or "").split(",") if s.strip()]
    request = ChiefOfStaffRequest(
        tenant_id=ctx.tenant_id,
        intent=ChiefOfStaffIntent(args.intent),
        target_type=ChiefOfStaffTargetType(args.target_type),
        target_id=args.target_id,
        as_of_at=_parse_as_of(args.as_of),
        horizon_days=args.horizon_days,
        scenario_run_ids=scenario_ids,
        prior_brief_id=args.prior_brief_id,
        requested_sections=sections,  # type: ignore[arg-type]
        requested_provider=ChiefOfStaffProviderMode(args.provider),
    )
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            service = ChiefOfStaffService(uow)
            outcome = service.generate(ctx, request)
            _print(_safe_outcome(outcome))
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_validate(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            result = ChiefOfStaffService(uow).validate_brief(ctx, args.brief_id)
            _print({"synthetic": _SYNTHETIC_BANNER, **result})
            return 0
        except (EnterpriseError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_compare(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            result = ChiefOfStaffService(uow).compare_briefs(
                ctx, args.current_brief_id, args.prior_brief_id
            )
            _print({"synthetic": _SYNTHETIC_BANNER, **result})
            return 0
        except (EnterpriseError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_review(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            review = ChiefOfStaffService(uow).append_review(
                ctx,
                brief_id=args.brief_id,
                review_state=ChiefOfStaffReviewState(args.state),
                reviewer_context=args.reviewer_context or "cli",
                notes=args.notes or "",
            )
            _print({"synthetic": _SYNTHETIC_BANNER, "review": _dump(review)})
            return 0
        except (EnterpriseError, ValueError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def cmd_quality(args: argparse.Namespace) -> int:
    ctx = TenantContext.require(args.tenant_id)
    with _session() as session:
        uow = UnitOfWork(session)
        summary = ChiefOfStaffService(uow).quality_summary(ctx)
        _print({"synthetic": _SYNTHETIC_BANNER, "quality": _dump(summary)})
        return 0


def cmd_seed_novabank(args: argparse.Namespace) -> int:
    from app.services.chief_of_staff.novabank_seed import seed_novabank_briefs

    ctx = TenantContext.require(args.tenant_id or "novabank")
    with _session() as session:
        uow = UnitOfWork(session)
        try:
            result = seed_novabank_briefs(uow, ctx, as_of=_parse_as_of(args.as_of) if args.as_of else None)
            uow.commit()
            _print({"synthetic": _SYNTHETIC_BANNER, **result})
            return 0
        except (EnterpriseError, ValueError, LookupError) as exc:
            uow.rollback()
            print(f"error: {exc}", file=sys.stderr)
            return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.chief_of_staff")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate an immutable Chief of Staff brief")
    gen.add_argument("--tenant-id", required=True)
    gen.add_argument("--intent", required=True, choices=[i.value for i in ChiefOfStaffIntent])
    gen.add_argument(
        "--target-type", required=True, choices=[t.value for t in ChiefOfStaffTargetType]
    )
    gen.add_argument("--target-id", required=True)
    gen.add_argument("--as-of", required=True, help="ISO-8601 cutoff")
    gen.add_argument("--horizon-days", type=int, default=None)
    gen.add_argument("--scenario-run-ids", default="", help="Comma-separated, max 10")
    gen.add_argument("--prior-brief-id", default=None)
    gen.add_argument("--sections", default="", help="Comma-separated section keys")
    gen.add_argument(
        "--provider",
        default=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK.value,
        choices=[p.value for p in ChiefOfStaffProviderMode],
    )
    gen.set_defaults(func=cmd_generate)

    val = sub.add_parser("validate", help="Validate a persisted brief")
    val.add_argument("--tenant-id", required=True)
    val.add_argument("--brief-id", required=True)
    val.set_defaults(func=cmd_validate)

    cmp_ = sub.add_parser("compare", help="Compare current and prior brief packages")
    cmp_.add_argument("--tenant-id", required=True)
    cmp_.add_argument("--current-brief-id", required=True)
    cmp_.add_argument("--prior-brief-id", required=True)
    cmp_.set_defaults(func=cmd_compare)

    rev = sub.add_parser("review", help="Append a human review (does not mutate brief)")
    rev.add_argument("--tenant-id", required=True)
    rev.add_argument("--brief-id", required=True)
    rev.add_argument("--state", required=True, choices=[s.value for s in ChiefOfStaffReviewState])
    rev.add_argument("--reviewer-context", default="cli")
    rev.add_argument("--notes", default="")
    rev.set_defaults(func=cmd_review)

    qual = sub.add_parser("quality", help="Inspect quality summary")
    qual.add_argument("--tenant-id", required=True)
    qual.set_defaults(func=cmd_quality)

    seed = sub.add_parser("seed-novabank", help="Generate bounded NovaBank demonstration briefs")
    seed.add_argument("--tenant-id", default="novabank")
    seed.add_argument("--as-of", default="2026-03-01T12:00:00+00:00")
    seed.set_defaults(func=cmd_seed_novabank)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
