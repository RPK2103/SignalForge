"""Observability & AI-quality CLI (Phase 3 Prompt 8).

Deterministic, offline commands for release gating and operational inspection.
No live provider is required; ``evaluate-ai-quality`` is the CI release gate and
exits non-zero on any critical safety violation.

Security: mutating/persisting commands run under an explicit, auditable trusted
internal context (:func:`internal_system_context`) and still pass through the
service-layer authorization check. No tokens, prompts or evidence are printed.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import get_engine, init_engine
from app.db.unit_of_work import UnitOfWork
from app.observability.evaluation import PROVIDER_PRIMARY, run_dataset
from app.observability.freshness import compute_freshness
from app.observability.prediction_quality import build_calibration_snapshot
from app.observability.release_dataset import build_release_cases
from app.security.context import internal_system_context
from app.services.observability.ai_quality_service import AiQualityService
from app.services.observability.observability_service import ObservabilityService


def _print(payload: dict | list) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _session() -> Session:
    init_engine()
    return Session(get_engine())


def _context(tenant_id: str):
    return internal_system_context(tenant_id, correlation_id=f"cli_{uuid.uuid4().hex[:12]}")


def _parse_dt(value: str) -> datetime:
    raw = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cmd_evaluate_ai_quality(args: argparse.Namespace) -> int:
    """Run the deterministic release-gate dataset. Non-zero exit on gate failure."""
    outcome = run_dataset(build_release_cases())
    summary = {
        "command": "evaluate-ai-quality",
        "tenant_id": args.tenant_id,
        "provider_variant": PROVIDER_PRIMARY,
        "total_cases": outcome.total_cases,
        "passed_cases": outcome.passed_cases,
        "failed_cases": outcome.failed_cases,
        "critical_violations": outcome.critical_violations,
        "aggregate_score": outcome.aggregate_score,
        "release_gate_passed": outcome.release_gate_passed,
        "failed": [
            {"case_key": r.case_key, "metric": r.metric, "severity": r.severity}
            for r in outcome.results
            if not r.passed
        ],
    }
    if args.persist:
        with _session() as session:
            uow = UnitOfWork(session)
            run = AiQualityService(uow).run_release_evaluation(_context(args.tenant_id))
            summary["persisted_run_id"] = run.id
    _print(summary)
    # Fail closed: any critical violation returns non-zero for CI.
    return 0 if outcome.release_gate_passed else 1


def cmd_evaluate_slos(args: argparse.Namespace) -> int:
    with _session() as session:
        uow = UnitOfWork(session)
        service = ObservabilityService(uow)
        ctx = _context(args.tenant_id)
        evaluations = service.evaluate_slos(ctx)
        _print(
            {
                "command": "evaluate-slos",
                "tenant_id": args.tenant_id,
                "evaluations": [e.model_dump(mode="json") for e in evaluations],
            }
        )
    return 0


def cmd_record_prediction_quality(args: argparse.Namespace) -> int:
    with open(args.input, encoding="utf-8") as handle:
        data = json.load(handle)
    probs = data.get("probabilities", [])
    outcomes = data.get("outcomes", [])
    snapshot = build_calibration_snapshot(probabilities=probs, outcomes=outcomes)
    payload = {
        "command": "record-prediction-quality",
        "tenant_id": args.tenant_id,
        "status": snapshot.status.value,
        "brier_score": snapshot.brier_score,
        "calibration_error": snapshot.calibration_error,
        "label_coverage": snapshot.label_coverage,
        "sample_count": snapshot.sample_count,
    }
    if args.persist:
        now = datetime.now(timezone.utc)
        with _session() as session:
            uow = UnitOfWork(session)
            record = uow.prediction_quality_snapshots.append(
                args.tenant_id,
                model_version=args.model_version,
                snapshot_type="calibration",
                window_start=now,
                window_end=now,
                data_cutoff=None,
                brier_score=snapshot.brier_score,
                calibration_error=snapshot.calibration_error,
                drift_score=None,
                drift_method=None,
                label_coverage=snapshot.label_coverage,
                sample_count=snapshot.sample_count,
                status=snapshot.status.value,
                distributions={
                    "prediction": snapshot.prediction_distribution,
                    "outcome": snapshot.outcome_distribution,
                },
                canonical_hash=uuid.uuid4().hex,
            )
            uow.commit()
            payload["persisted_id"] = record.id
    _print(payload)
    return 0


def cmd_inspect_freshness(args: argparse.Namespace) -> int:
    latest = _parse_dt(args.latest_event) if args.latest_event else None
    evaluation_time = _parse_dt(args.evaluation_time) if args.evaluation_time else None
    result = compute_freshness(
        source_type=args.source_type,
        latest_source_event_time=latest,
        evaluation_time=evaluation_time,
        has_successful_checkpoint=not args.no_checkpoint,
    )
    _print(
        {
            "command": "inspect-freshness",
            "source_type": args.source_type,
            "status": result.status.value,
            "age_seconds": result.age_seconds,
            "stale_threshold_seconds": result.stale_threshold_seconds,
            "clock_skew": result.clock_skew,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.observability")
    sub = parser.add_subparsers(dest="command", required=True)

    ai = sub.add_parser("evaluate-ai-quality", help="Run the deterministic AI release gate")
    ai.add_argument("--tenant-id", default="release-tenant")
    ai.add_argument("--persist", action="store_true", help="Also persist a run (requires DB)")
    ai.set_defaults(func=cmd_evaluate_ai_quality)

    slo = sub.add_parser("evaluate-slos", help="Evaluate SLOs and sync alerts")
    slo.add_argument("--tenant-id", required=True)
    slo.set_defaults(func=cmd_evaluate_slos)

    pq = sub.add_parser("record-prediction-quality", help="Compute a calibration snapshot")
    pq.add_argument("--tenant-id", required=True)
    pq.add_argument("--input", required=True, help="JSON with probabilities/outcomes arrays")
    pq.add_argument("--model-version", default=None)
    pq.add_argument("--persist", action="store_true")
    pq.set_defaults(func=cmd_record_prediction_quality)

    fr = sub.add_parser("inspect-freshness", help="Compute freshness for a source")
    fr.add_argument("--source-type", required=True)
    fr.add_argument("--latest-event", default=None, help="ISO-8601 latest source event time")
    fr.add_argument("--evaluation-time", default=None, help="ISO-8601 evaluation time")
    fr.add_argument("--no-checkpoint", action="store_true")
    fr.set_defaults(func=cmd_inspect_freshness)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
