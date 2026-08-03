"""Tenant-scoped observability & AI-quality repositories (Phase 3 Prompt 8).

Every query is qualified by ``tenant_id`` (application isolation), and every
table carries a NOT NULL ``tenant_id`` so PostgreSQL forced-RLS is the defense in
depth. Evaluation results are append-only; alerts are deduplicated by a stable
fingerprint with an append-only transition history.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.observability import (
    AiEvaluationCase,
    AiEvaluationDataset,
    AiEvaluationResult,
    AiEvaluationRun,
    AlertEvent,
    ObservabilityMetricRollup,
    PredictionQualitySnapshot,
    SloDefinition,
    SloEvaluation,
)
from app.domain.observability_models import (
    AlertEventRecord,
    EvaluationDatasetRecord,
    EvaluationResultRecord,
    EvaluationRunRecord,
    MetricRollupRecord,
    PredictionQualitySnapshotRecord,
    SloDefinitionRecord,
    SloEvaluationRecord,
)

_MAX_PAGE = 100


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_limit(limit: int) -> int:
    return max(1, min(int(limit), _MAX_PAGE))


class MetricRollupRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        tenant_id: str,
        *,
        metric_name: str,
        window_start: datetime,
        window_end: datetime,
        value: float,
        unit: str,
        sample_count: int,
        dimensions: dict[str, Any],
        canonical_hash: str,
        service_version: str = "0.0.0",
    ) -> MetricRollupRecord:
        existing = self._session.scalar(
            select(ObservabilityMetricRollup).where(
                ObservabilityMetricRollup.tenant_id == tenant_id,
                ObservabilityMetricRollup.metric_name == metric_name,
                ObservabilityMetricRollup.window_start == window_start,
                ObservabilityMetricRollup.window_end == window_end,
                ObservabilityMetricRollup.canonical_hash == canonical_hash,
            )
        )
        if existing is not None:
            existing.value = value
            existing.sample_count = sample_count
            existing.dimensions = dimensions
            self._session.flush()
            return MetricRollupRecord.model_validate(existing)
        row = ObservabilityMetricRollup(
            id=new_id("obsr"),
            tenant_id=tenant_id,
            metric_name=metric_name,
            window_start=window_start,
            window_end=window_end,
            value=value,
            unit=unit,
            sample_count=sample_count,
            dimensions=dimensions,
            service_version=service_version,
            canonical_hash=canonical_hash,
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return MetricRollupRecord.model_validate(row)

    def list(
        self,
        tenant_id: str,
        *,
        metric_name: str | None = None,
        limit: int = 50,
    ) -> list[MetricRollupRecord]:
        stmt = select(ObservabilityMetricRollup).where(
            ObservabilityMetricRollup.tenant_id == tenant_id
        )
        if metric_name:
            stmt = stmt.where(ObservabilityMetricRollup.metric_name == metric_name)
        stmt = stmt.order_by(
            ObservabilityMetricRollup.window_start.desc(),
            ObservabilityMetricRollup.id.desc(),
        ).limit(_bounded_limit(limit))
        return [MetricRollupRecord.model_validate(r) for r in self._session.scalars(stmt).all()]


class SloDefinitionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        tenant_id: str,
        *,
        slo_key: str,
        indicator: str,
        objective: float,
        comparison: str,
        unit: str,
        window_seconds: int,
        min_sample_count: int,
        description: str,
    ) -> SloDefinitionRecord:
        latest = self._session.scalar(
            select(SloDefinition)
            .where(SloDefinition.tenant_id == tenant_id, SloDefinition.slo_key == slo_key)
            .order_by(SloDefinition.version.desc())
        )
        version = (latest.version + 1) if latest is not None else 1
        row = SloDefinition(
            id=new_id("slo"),
            tenant_id=tenant_id,
            slo_key=slo_key,
            version=version,
            indicator=indicator,
            objective=objective,
            comparison=comparison,
            unit=unit,
            window_seconds=window_seconds,
            min_sample_count=min_sample_count,
            description=description,
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return SloDefinitionRecord.model_validate(row)

    def get_latest(self, tenant_id: str, slo_key: str) -> SloDefinitionRecord | None:
        row = self._session.scalar(
            select(SloDefinition)
            .where(SloDefinition.tenant_id == tenant_id, SloDefinition.slo_key == slo_key)
            .order_by(SloDefinition.version.desc())
        )
        return SloDefinitionRecord.model_validate(row) if row else None

    def list_latest(self, tenant_id: str, *, limit: int = 50) -> list[SloDefinitionRecord]:
        rows = self._session.scalars(
            select(SloDefinition)
            .where(SloDefinition.tenant_id == tenant_id)
            .order_by(SloDefinition.slo_key, SloDefinition.version.desc())
        ).all()
        latest: dict[str, SloDefinition] = {}
        for row in rows:
            if row.slo_key not in latest:
                latest[row.slo_key] = row
        records = [SloDefinitionRecord.model_validate(r) for r in latest.values()]
        return records[: _bounded_limit(limit)]


class SloEvaluationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        tenant_id: str,
        *,
        slo_key: str,
        slo_version: int,
        indicator: str,
        window_start: datetime,
        window_end: datetime,
        evaluation_cutoff: datetime,
        observed_value: float | None,
        objective: float,
        sample_count: int,
        status: str,
        canonical_hash: str,
        metadata: dict[str, Any] | None = None,
    ) -> SloEvaluationRecord:
        row = SloEvaluation(
            id=new_id("sloe"),
            tenant_id=tenant_id,
            slo_key=slo_key,
            slo_version=slo_version,
            indicator=indicator,
            window_start=window_start,
            window_end=window_end,
            evaluation_cutoff=evaluation_cutoff,
            observed_value=observed_value,
            objective=objective,
            sample_count=sample_count,
            status=status,
            event_metadata=metadata or {},
            canonical_hash=canonical_hash,
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return SloEvaluationRecord.model_validate(row)

    def list(
        self, tenant_id: str, *, slo_key: str | None = None, limit: int = 50
    ) -> list[SloEvaluationRecord]:
        stmt = select(SloEvaluation).where(SloEvaluation.tenant_id == tenant_id)
        if slo_key:
            stmt = stmt.where(SloEvaluation.slo_key == slo_key)
        stmt = stmt.order_by(SloEvaluation.created_at.desc(), SloEvaluation.id.desc()).limit(
            _bounded_limit(limit)
        )
        return [SloEvaluationRecord.model_validate(r) for r in self._session.scalars(stmt).all()]


class AlertEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_fingerprint(self, tenant_id: str, fingerprint: str) -> AlertEvent | None:
        return self._session.scalar(
            select(AlertEvent).where(
                AlertEvent.tenant_id == tenant_id, AlertEvent.fingerprint == fingerprint
            )
        )

    def get(self, tenant_id: str, alert_id: str) -> AlertEvent | None:
        return self._session.scalar(
            select(AlertEvent).where(AlertEvent.tenant_id == tenant_id, AlertEvent.id == alert_id)
        )

    def upsert_open(
        self,
        tenant_id: str,
        *,
        fingerprint: str,
        severity: str,
        source: str,
        title: str,
        reason_code: str,
        correlated_slo_key: str | None = None,
        correlated_run_id: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AlertEventRecord, bool]:
        """Open (or refresh) an alert. Returns (record, created).

        Deduplicates: an existing non-resolved alert with the same fingerprint is
        refreshed in place (no duplicate open alert). A resolved alert with the
        same fingerprint is re-opened with an appended transition.
        """
        now = _utcnow()
        existing = self.get_by_fingerprint(tenant_id, fingerprint)
        if existing is not None:
            created = False
            if existing.state == "resolved":
                existing.transitions = [
                    *existing.transitions,
                    {
                        "from": "resolved",
                        "to": "open",
                        "at": now.isoformat(),
                        "reason": reason_code,
                    },
                ]
                existing.state = "open"
                existing.resolved_at = None
            existing.severity = severity
            existing.title = title
            existing.reason_code = reason_code
            existing.updated_at = now
            existing.window_start = window_start
            existing.window_end = window_end
            if metadata is not None:
                existing.event_metadata = metadata
            self._session.flush()
            return AlertEventRecord.model_validate(existing), created
        row = AlertEvent(
            id=new_id("alrt"),
            tenant_id=tenant_id,
            fingerprint=fingerprint,
            severity=severity,
            state="open",
            source=source,
            title=title,
            reason_code=reason_code,
            correlated_slo_key=correlated_slo_key,
            correlated_run_id=correlated_run_id,
            window_start=window_start,
            window_end=window_end,
            opened_at=now,
            updated_at=now,
            transitions=[
                {"from": None, "to": "open", "at": now.isoformat(), "reason": reason_code}
            ],
            event_metadata=metadata or {},
        )
        self._session.add(row)
        self._session.flush()
        return AlertEventRecord.model_validate(row), True

    def transition(
        self,
        row: AlertEvent,
        *,
        new_state: str,
        actor_hash: str | None = None,
        reason: str = "",
    ) -> AlertEventRecord:
        now = _utcnow()
        row.transitions = [
            *row.transitions,
            {"from": row.state, "to": new_state, "at": now.isoformat(), "reason": reason},
        ]
        row.state = new_state
        row.updated_at = now
        if new_state == "acknowledged":
            row.acknowledged_by_hash = actor_hash
        if new_state == "resolved":
            row.resolved_at = now
        self._session.flush()
        return AlertEventRecord.model_validate(row)

    def list(
        self, tenant_id: str, *, state: str | None = None, limit: int = 50
    ) -> list[AlertEventRecord]:
        stmt = select(AlertEvent).where(AlertEvent.tenant_id == tenant_id)
        if state:
            stmt = stmt.where(AlertEvent.state == state)
        stmt = stmt.order_by(AlertEvent.updated_at.desc(), AlertEvent.id.desc()).limit(
            _bounded_limit(limit)
        )
        return [AlertEventRecord.model_validate(r) for r in self._session.scalars(stmt).all()]


class AiEvaluationDatasetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        tenant_id: str,
        *,
        dataset_key: str,
        name: str,
        description: str,
        data_cutoff: datetime | None,
        prompt_version: str | None,
        case_count: int,
        canonical_hash: str,
        published: bool = True,
    ) -> EvaluationDatasetRecord:
        latest = self._session.scalar(
            select(AiEvaluationDataset)
            .where(
                AiEvaluationDataset.tenant_id == tenant_id,
                AiEvaluationDataset.dataset_key == dataset_key,
            )
            .order_by(AiEvaluationDataset.version.desc())
        )
        # A published dataset is immutable: only re-publish when content changed.
        if latest is not None and latest.canonical_hash == canonical_hash:
            return EvaluationDatasetRecord.model_validate(latest)
        version = (latest.version + 1) if latest is not None else 1
        row = AiEvaluationDataset(
            id=new_id("aids"),
            tenant_id=tenant_id,
            dataset_key=dataset_key,
            version=version,
            name=name,
            description=description,
            data_cutoff=data_cutoff,
            prompt_version=prompt_version,
            published=1 if published else 0,
            case_count=case_count,
            canonical_hash=canonical_hash,
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return EvaluationDatasetRecord.model_validate(row)

    def get_latest(self, tenant_id: str, dataset_key: str) -> AiEvaluationDataset | None:
        return self._session.scalar(
            select(AiEvaluationDataset)
            .where(
                AiEvaluationDataset.tenant_id == tenant_id,
                AiEvaluationDataset.dataset_key == dataset_key,
            )
            .order_by(AiEvaluationDataset.version.desc())
        )


class AiEvaluationCaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_cases(
        self, tenant_id: str, dataset_id: str, cases: Sequence[dict[str, Any]]
    ) -> int:
        # Cases are immutable per dataset version; only inserted for a new version.
        existing = self._session.scalars(
            select(AiEvaluationCase).where(
                AiEvaluationCase.tenant_id == tenant_id,
                AiEvaluationCase.dataset_id == dataset_id,
            )
        ).all()
        if existing:
            return len(existing)
        count = 0
        for case in cases:
            row = AiEvaluationCase(
                id=new_id("aic"),
                tenant_id=tenant_id,
                dataset_id=dataset_id,
                case_key=case["case_key"],
                category=case["category"],
                intent=case.get("intent"),
                expected=case.get("expected", {}),
                payload=case.get("payload", {}),
                data_cutoff=case.get("data_cutoff"),
                prompt_version=case.get("prompt_version"),
                provider_version=case.get("provider_version"),
                canonical_hash=case["canonical_hash"],
                created_at=_utcnow(),
            )
            self._session.add(row)
            count += 1
        self._session.flush()
        return count

    def list_for_dataset(self, tenant_id: str, dataset_id: str) -> list[AiEvaluationCase]:
        return list(
            self._session.scalars(
                select(AiEvaluationCase)
                .where(
                    AiEvaluationCase.tenant_id == tenant_id,
                    AiEvaluationCase.dataset_id == dataset_id,
                )
                .order_by(AiEvaluationCase.case_key)
            ).all()
        )


class AiEvaluationRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        tenant_id: str,
        *,
        dataset_id: str,
        dataset_version: int,
        run_key: str,
        provider_variant: str,
        prompt_version: str,
        status: str,
        total_cases: int,
        passed_cases: int,
        failed_cases: int,
        aggregate_score: float | None,
        release_gate_passed: bool | None,
        critical_violations: int,
        started_at: datetime,
        completed_at: datetime | None,
        canonical_hash: str,
        metadata: dict[str, Any] | None = None,
    ) -> EvaluationRunRecord:
        row = AiEvaluationRun(
            id=new_id("air"),
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            run_key=run_key,
            provider_variant=provider_variant,
            prompt_version=prompt_version,
            status=status,
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            aggregate_score=aggregate_score,
            release_gate_passed=(None if release_gate_passed is None else int(release_gate_passed)),
            critical_violations=critical_violations,
            started_at=started_at,
            completed_at=completed_at,
            event_metadata=metadata or {},
            canonical_hash=canonical_hash,
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return EvaluationRunRecord.model_validate(row)

    def get(self, tenant_id: str, run_id: str) -> EvaluationRunRecord | None:
        row = self._session.scalar(
            select(AiEvaluationRun).where(
                AiEvaluationRun.tenant_id == tenant_id, AiEvaluationRun.id == run_id
            )
        )
        return EvaluationRunRecord.model_validate(row) if row else None

    def list(self, tenant_id: str, *, limit: int = 50) -> list[EvaluationRunRecord]:
        stmt = (
            select(AiEvaluationRun)
            .where(AiEvaluationRun.tenant_id == tenant_id)
            .order_by(AiEvaluationRun.created_at.desc(), AiEvaluationRun.id.desc())
            .limit(_bounded_limit(limit))
        )
        return [EvaluationRunRecord.model_validate(r) for r in self._session.scalars(stmt).all()]


class AiEvaluationResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        tenant_id: str,
        *,
        run_id: str,
        case_key: str,
        category: str,
        metric: str,
        value: float | None,
        threshold: float | None,
        status: str,
        severity: str,
        passed: bool,
        detail: dict[str, Any],
        canonical_hash: str,
    ) -> EvaluationResultRecord:
        row = AiEvaluationResult(
            id=new_id("aires"),
            tenant_id=tenant_id,
            run_id=run_id,
            case_key=case_key,
            category=category,
            metric=metric,
            value=value,
            threshold=threshold,
            status=status,
            severity=severity,
            passed=1 if passed else 0,
            detail=detail,
            canonical_hash=canonical_hash,
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return EvaluationResultRecord.model_validate(row)

    def list_for_run(self, tenant_id: str, run_id: str) -> list[EvaluationResultRecord]:
        rows = self._session.scalars(
            select(AiEvaluationResult)
            .where(
                AiEvaluationResult.tenant_id == tenant_id,
                AiEvaluationResult.run_id == run_id,
            )
            .order_by(AiEvaluationResult.case_key, AiEvaluationResult.metric)
        ).all()
        return [EvaluationResultRecord.model_validate(r) for r in rows]


class PredictionQualitySnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        tenant_id: str,
        *,
        model_version: str | None,
        snapshot_type: str,
        window_start: datetime,
        window_end: datetime,
        data_cutoff: datetime | None,
        brier_score: float | None,
        calibration_error: float | None,
        drift_score: float | None,
        drift_method: str | None,
        label_coverage: float | None,
        sample_count: int,
        status: str,
        distributions: dict[str, Any],
        canonical_hash: str,
    ) -> PredictionQualitySnapshotRecord:
        row = PredictionQualitySnapshot(
            id=new_id("pqs"),
            tenant_id=tenant_id,
            model_version=model_version,
            snapshot_type=snapshot_type,
            window_start=window_start,
            window_end=window_end,
            data_cutoff=data_cutoff,
            brier_score=brier_score,
            calibration_error=calibration_error,
            drift_score=drift_score,
            drift_method=drift_method,
            label_coverage=label_coverage,
            sample_count=sample_count,
            status=status,
            distributions=distributions,
            canonical_hash=canonical_hash,
            created_at=_utcnow(),
        )
        self._session.add(row)
        self._session.flush()
        return PredictionQualitySnapshotRecord.model_validate(row)

    def list(
        self, tenant_id: str, *, model_version: str | None = None, limit: int = 50
    ) -> list[PredictionQualitySnapshotRecord]:
        stmt = select(PredictionQualitySnapshot).where(
            PredictionQualitySnapshot.tenant_id == tenant_id
        )
        if model_version:
            stmt = stmt.where(PredictionQualitySnapshot.model_version == model_version)
        stmt = stmt.order_by(
            PredictionQualitySnapshot.created_at.desc(), PredictionQualitySnapshot.id.desc()
        ).limit(_bounded_limit(limit))
        return [
            PredictionQualitySnapshotRecord.model_validate(r)
            for r in self._session.scalars(stmt).all()
        ]
