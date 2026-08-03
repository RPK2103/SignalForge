"""AI-quality evaluation application service (Phase 3 Prompt 8).

Reads require ``ai_quality.read``; running an evaluation requires
``ai_quality.evaluate`` and emits a security audit event. Evaluations are fully
deterministic and offline (no live LLM), so results are reproducible in CI.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.db.unit_of_work import UnitOfWork
from app.domain.observability_models import (
    EvaluationRunRecord,
    EvaluationStatus,
)
from app.observability import evaluation as ev
from app.observability.release_dataset import (
    PROMPT_VERSION,
    RELEASE_DATASET_KEY,
    build_release_cases,
)
from app.security.audit import SecurityAuditService
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.enums import Permission, SecurityAuditAction


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class AiQualityService:
    def __init__(self, uow: UnitOfWork, authz: AuthorizationService | None = None) -> None:
        self._uow = uow
        self._authz = authz or AuthorizationService()
        self._audit = SecurityAuditService(uow)

    # -- reads -------------------------------------------------------------
    def list_runs(self, context: SecurityContext, *, limit: int = 50) -> list[EvaluationRunRecord]:
        self._authz.require_context(context, Permission.AI_QUALITY_READ)
        return self._uow.ai_evaluation_runs.list(context.tenant_id, limit=limit)

    def get_run(self, context: SecurityContext, *, run_id: str) -> dict | None:
        self._authz.require_context(context, Permission.AI_QUALITY_READ)
        run = self._uow.ai_evaluation_runs.get(context.tenant_id, run_id)
        if run is None:
            return None
        results = self._uow.ai_evaluation_results.list_for_run(context.tenant_id, run_id)
        return {
            "run": run.model_dump(mode="json"),
            "results": [r.model_dump(mode="json") for r in results],
        }

    # -- evaluation --------------------------------------------------------
    def publish_release_dataset(self, context: SecurityContext):
        """Publish (immutably) the deterministic release dataset for this tenant."""
        self._authz.require_context(context, Permission.AI_QUALITY_EVALUATE)
        cases = build_release_cases()
        case_payload = [
            {
                "case_key": c.case_key,
                "category": c.category.value,
                "intent": c.intent,
                "expected": {
                    "decision": c.expected_decision,
                    "expect_refusal": c.expect_refusal,
                },
                "payload": {"required_classes": list(c.required_classes)},
                "prompt_version": c.prompt_version,
                "canonical_hash": c.canonical_hash(),
            }
            for c in cases
        ]
        dataset_hash = _hash([c["canonical_hash"] for c in case_payload])
        dataset = self._uow.ai_evaluation_datasets.upsert(
            context.tenant_id,
            dataset_key=RELEASE_DATASET_KEY,
            name="Release Gate Core",
            description="Deterministic offline AI-quality release dataset.",
            data_cutoff=None,
            prompt_version=PROMPT_VERSION,
            case_count=len(cases),
            canonical_hash=dataset_hash,
        )
        latest = self._uow.ai_evaluation_datasets.get_latest(context.tenant_id, RELEASE_DATASET_KEY)
        if latest is not None:
            for cp in case_payload:
                cp["data_cutoff"] = None
            self._uow.ai_evaluation_cases.replace_cases(context.tenant_id, latest.id, case_payload)
        self._uow.commit()
        return dataset

    def run_release_evaluation(
        self, context: SecurityContext, *, provider_variant: str = ev.PROVIDER_PRIMARY
    ) -> EvaluationRunRecord:
        self._authz.require_context(context, Permission.AI_QUALITY_EVALUATE)
        dataset = self.publish_release_dataset(context)
        cases = build_release_cases()
        started = _utcnow()

        try:
            outcome = ev.run_dataset(cases)
            status = EvaluationStatus.COMPLETED
        except Exception:  # noqa: BLE001 - persist the failure safely; never crash
            status = EvaluationStatus.FAILED
            run = self._uow.ai_evaluation_runs.create(
                context.tenant_id,
                dataset_id=dataset.id,
                dataset_version=dataset.version,
                run_key=f"run_{started.strftime('%Y%m%d%H%M%S')}",
                provider_variant=provider_variant,
                prompt_version=PROMPT_VERSION,
                status=status.value,
                total_cases=len(cases),
                passed_cases=0,
                failed_cases=len(cases),
                aggregate_score=None,
                release_gate_passed=False,
                critical_violations=1,
                started_at=started,
                completed_at=_utcnow(),
                canonical_hash=_hash({"dataset": dataset.id, "status": "failed"}),
            )
            self._uow.commit()
            return run

        run_key = f"run_{started.strftime('%Y%m%d%H%M%S')}_{provider_variant}"
        run = self._uow.ai_evaluation_runs.create(
            context.tenant_id,
            dataset_id=dataset.id,
            dataset_version=dataset.version,
            run_key=run_key,
            provider_variant=provider_variant,
            prompt_version=PROMPT_VERSION,
            status=status.value,
            total_cases=outcome.total_cases,
            passed_cases=outcome.passed_cases,
            failed_cases=outcome.failed_cases,
            aggregate_score=outcome.aggregate_score,
            release_gate_passed=outcome.release_gate_passed,
            critical_violations=outcome.critical_violations,
            started_at=started,
            completed_at=_utcnow(),
            canonical_hash=_hash(
                {
                    "dataset": dataset.id,
                    "aggregate": outcome.aggregate_score,
                    "gate": outcome.release_gate_passed,
                }
            ),
        )
        for result in outcome.results:
            self._uow.ai_evaluation_results.append(
                context.tenant_id,
                run_id=run.id,
                case_key=result.case_key,
                category=result.category.value,
                metric=result.metric,
                value=result.value,
                threshold=result.threshold,
                status=result.status.value,
                severity=result.severity,
                passed=result.passed,
                detail=result.detail,
                canonical_hash=result.canonical_hash(),
            )
        self._audit.record_sensitive_action(
            context,
            action=SecurityAuditAction.AI_QUALITY_EVALUATED,
            permission=Permission.AI_QUALITY_EVALUATE,
            resource_type="ai_evaluation_run",
            resource_id=run.id,
            metadata={
                "release_gate_passed": outcome.release_gate_passed,
                "critical_violations": outcome.critical_violations,
            },
        )
        self._uow.commit()
        return run
