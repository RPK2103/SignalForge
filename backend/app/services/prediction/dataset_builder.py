"""Deterministic temporal dataset construction for delivery prediction."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.db.unit_of_work import UnitOfWork
from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_constants import (
    CALIBRATION_FRACTION,
    DEFAULT_HORIZON_DAYS,
    FEATURE_SCHEMA_VERSION,
    LABEL_VERSION,
    MIN_CALIBRATION_ROWS,
    MIN_LABELED_ROWS,
    MIN_NEGATIVE_ROWS,
    MIN_POSITIVE_ROWS,
    MIN_TEST_ROWS,
    SPLIT_STRATEGY,
    TARGET_DEFINITION,
    TRAIN_FRACTION,
)
from app.domain.prediction_enums import (
    OutcomeCategory,
    PredictionDataScope,
    VerificationStatus,
)
from app.domain.prediction_models import (
    DeliveryOutcome,
    PredictionDatasetManifest,
    PredictionFeatureSnapshot,
    validate_horizon,
)
from app.domain.tenant_context import TenantContext
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction.feature_extractor import FeatureExtractor
from app.services.prediction.feature_schema import FEATURE_NAMES
from app.services.prediction.leakage import PredictionLeakageValidator

logger = logging.getLogger("signalforge.prediction")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class PredictionDatasetBuilder:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._extractor = FeatureExtractor(uow)
        self._leakage = PredictionLeakageValidator()

    def build(
        self,
        ctx: TenantContext,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> PredictionDatasetManifest:
        horizon_days = validate_horizon(horizon_days)
        generated_at = _utcnow()

        raw_outcomes = self._load_candidate_outcomes(ctx, horizon_days)
        exclusion_reasons: dict[str, int] = defaultdict(int)
        eligible: list[DeliveryOutcome] = []
        censored_rows = 0

        for outcome in raw_outcomes:
            reason = self._exclusion_reason(outcome)
            if reason is not None:
                exclusion_reasons[reason] += 1
                if outcome.outcome_category in {
                    OutcomeCategory.UNKNOWN,
                    OutcomeCategory.CENSORED,
                }:
                    censored_rows += 1
                continue
            eligible.append(outcome)

        clean_rows: list[tuple[DeliveryOutcome, PredictionFeatureSnapshot]] = []
        leakage_rows: list[dict[str, Any]] = []
        leakage_rejection_reasons: dict[str, int] = defaultdict(int)
        rows_examined = 0
        rows_rejected = 0

        for outcome in eligible:
            snapshot = self._extractor.extract(
                ctx,
                outcome.target_type,
                outcome.target_id,
                outcome.prediction_cutoff_at,
                horizon_days=outcome.horizon_days,
                data_scope=outcome.data_scope,
            )

            rows_examined += 1
            leakage_row = self._leakage_row(outcome, snapshot)
            reasons = self._leakage.validate_row(
                leakage_row,
                prediction_cutoff_at=outcome.prediction_cutoff_at,
            )
            if reasons:
                rows_rejected += 1
                for reason in reasons:
                    leakage_rejection_reasons[reason] += 1
                exclusion_reasons["leakage_rejected"] += 1
                continue

            clean_rows.append((outcome, snapshot))
            leakage_rows.append(leakage_row)

        report = self._leakage.validate_dataset(leakage_rows)
        # Include previously rejected rows in the persisted hash payload.
        if rows_rejected:
            rejection_payload = {
                "rows_examined": rows_examined,
                "rows_rejected": rows_rejected,
                "rejection_reasons": dict(sorted(leakage_rejection_reasons.items())),
                "suspicious_features": report.suspicious_features,
                "latest_source_timestamp": (
                    report.latest_source_timestamp.isoformat()
                    if report.latest_source_timestamp
                    else None
                ),
                "cutoff_violations": report.cutoff_violations
                + sum(
                    1
                    for reason, count in leakage_rejection_reasons.items()
                    for _ in range(count)
                    if "after_cutoff" in reason or reason.startswith("post_cutoff_")
                ),
                "clean": False,
            }
            leakage_report_hash = snapshot_hash(rejection_payload)
            leakage_clean = False
        else:
            leakage_report_hash = report.report_hash
            leakage_clean = report.clean

        train_ids, cal_ids, test_ids = self._temporal_grouped_split(clean_rows)

        positive_rows = sum(1 for o, _ in clean_rows if o.binary_label == 1)
        negative_rows = sum(1 for o, _ in clean_rows if o.binary_label == 0)
        labeled_rows = len(clean_rows)
        excluded_rows = sum(exclusion_reasons.values())

        sufficiency_report = self._sufficiency_report(
            labeled_rows=labeled_rows,
            positive_rows=positive_rows,
            negative_rows=negative_rows,
            calibration_rows=len(cal_ids),
            test_rows=len(test_ids),
            leakage_clean=leakage_clean,
        )
        sufficiency_passed = bool(sufficiency_report["passed"])

        cutoffs = [_aware(o.prediction_cutoff_at) for o, _ in clean_rows]
        if cutoffs:
            minimum_cutoff_at = min(cutoffs)
            maximum_cutoff_at = max(cutoffs)
        else:
            minimum_cutoff_at = generated_at
            maximum_cutoff_at = generated_at

        data_scope = self._resolve_data_scope(clean_rows)
        source_high_watermarks: dict[str, str] = {}
        for _, snap in clean_rows:
            for key, value in snap.source_high_watermarks.items():
                prev = source_high_watermarks.get(key)
                if prev is None or str(value) > prev:
                    source_high_watermarks[key] = str(value)

        train_row_ids_hash = snapshot_hash(train_ids)
        calibration_row_ids_hash = snapshot_hash(cal_ids)
        test_row_ids_hash = snapshot_hash(test_ids)

        dataset_body = {
            "target_definition": TARGET_DEFINITION,
            "label_version": LABEL_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "horizon_days": horizon_days,
            "tenant_id": ctx.tenant_id,
            "split_strategy": SPLIT_STRATEGY,
            "train_row_ids": train_ids,
            "calibration_row_ids": cal_ids,
            "test_row_ids": test_ids,
            "leakage_report_hash": leakage_report_hash,
            "positive_rows": positive_rows,
            "negative_rows": negative_rows,
            "labeled_rows": labeled_rows,
            "feature_count": len(FEATURE_NAMES),
            "data_scope": data_scope.value,
        }
        dataset_hash = snapshot_hash(dataset_body)

        existing = None
        get_by_hash = getattr(self._uow.prediction_datasets, "get_by_hash", None)
        if callable(get_by_hash):
            existing = get_by_hash(ctx, dataset_hash)
        if existing is not None:
            logger.info(
                "prediction.dataset.reuse tenant_id=%s manifest_id=%s dataset_hash=%s",
                ctx.tenant_id,
                existing.prediction_dataset_manifest_id,
                dataset_hash,
            )
            return existing

        manifest_id = build_entity_id(
            "pdm",
            ctx.tenant_id,
            TARGET_DEFINITION,
            str(horizon_days),
            dataset_hash[:24],
        )
        manifest = PredictionDatasetManifest(
            tenant_id=ctx.tenant_id,
            prediction_dataset_manifest_id=manifest_id,
            target_definition=TARGET_DEFINITION,
            label_version=LABEL_VERSION,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            horizon_days=horizon_days,
            generated_at=generated_at,
            minimum_cutoff_at=minimum_cutoff_at,
            maximum_cutoff_at=maximum_cutoff_at,
            total_rows=labeled_rows + excluded_rows,
            labeled_rows=labeled_rows,
            excluded_rows=excluded_rows,
            positive_rows=positive_rows,
            negative_rows=negative_rows,
            censored_rows=censored_rows,
            tenant_count=1,
            feature_count=len(FEATURE_NAMES),
            split_strategy=SPLIT_STRATEGY,
            train_row_ids_hash=train_row_ids_hash,
            calibration_row_ids_hash=calibration_row_ids_hash,
            test_row_ids_hash=test_row_ids_hash,
            leakage_report_hash=leakage_report_hash,
            dataset_hash=dataset_hash,
            data_scope=data_scope,
            source_high_watermarks=source_high_watermarks,
            exclusion_reasons=dict(sorted(exclusion_reasons.items())),
            sufficiency_passed=sufficiency_passed,
            sufficiency_report=sufficiency_report,
            train_row_ids=train_ids,
            calibration_row_ids=cal_ids,
            test_row_ids=test_ids,
            created_at=generated_at,
        )
        self._uow.prediction_datasets.insert(ctx, manifest)
        logger.info(
            "prediction.dataset.built tenant_id=%s manifest_id=%s labeled=%s "
            "sufficiency=%s leakage_clean=%s",
            ctx.tenant_id,
            manifest_id,
            labeled_rows,
            sufficiency_passed,
            leakage_clean,
        )
        return manifest

    def _load_candidate_outcomes(
        self, ctx: TenantContext, horizon_days: int
    ) -> list[DeliveryOutcome]:
        # Prefer full horizon listing (includes censored/excluded for accounting).
        list_for_horizon = getattr(self._uow.delivery_outcomes, "list_for_horizon", None)
        if callable(list_for_horizon):
            return list(list_for_horizon(ctx, horizon_days=horizon_days, limit=500))
        list_labeled = getattr(self._uow.delivery_outcomes, "list_labeled", None)
        if callable(list_labeled):
            page = list_labeled(ctx, horizon_days=horizon_days, limit=100)
            items = getattr(page, "items", None)
            if items is not None:
                # Paginate until exhausted (Page max 100).
                collected = list(items)
                offset = len(collected)
                total = int(getattr(page, "total", offset))
                while offset < total:
                    page = list_labeled(ctx, horizon_days=horizon_days, limit=100, offset=offset)
                    batch = list(getattr(page, "items", []) or [])
                    if not batch:
                        break
                    collected.extend(batch)
                    offset += len(batch)
                return collected
            return list(page)
        raise AttributeError(
            "UnitOfWork.delivery_outcomes must provide list_labeled or list_for_horizon"
        )

    @staticmethod
    def _leakage_row(
        outcome: DeliveryOutcome,
        snapshot: PredictionFeatureSnapshot,
    ) -> dict[str, Any]:
        lineage = [
            entry.model_dump(mode="json") if hasattr(entry, "model_dump") else entry
            for entry in snapshot.feature_lineage
        ]
        return {
            "delivery_outcome_id": outcome.delivery_outcome_id,
            "prediction_cutoff_at": outcome.prediction_cutoff_at,
            "as_of_at": snapshot.as_of_at,
            "evidence_cutoff_at": snapshot.evidence_cutoff_at,
            "actual_completed_at": outcome.actual_completed_at,
            "outcome_category": outcome.outcome_category.value
            if hasattr(outcome.outcome_category, "value")
            else outcome.outcome_category,
            "binary_label": outcome.binary_label,
            "feature_values": dict(snapshot.feature_values),
            "feature_lineage": lineage,
            "source_timestamps": dict(snapshot.source_high_watermarks),
            "uses_current_graph_state": False,
        }

    @staticmethod
    def _exclusion_reason(outcome: DeliveryOutcome) -> str | None:
        if outcome.outcome_category in {OutcomeCategory.UNKNOWN, OutcomeCategory.CENSORED}:
            return f"category_{outcome.outcome_category.value}"
        if outcome.verification_status == VerificationStatus.DISPUTED:
            return "verification_disputed"
        if outcome.verification_status == VerificationStatus.EXCLUDED:
            return "verification_excluded"
        if outcome.verification_status != VerificationStatus.VERIFIED:
            return f"verification_{outcome.verification_status.value}"
        if outcome.finalized_at is None:
            return "not_finalized"
        if outcome.binary_label not in (0, 1):
            return "missing_binary_label"
        return None

    def _temporal_grouped_split(
        self,
        rows: list[tuple[DeliveryOutcome, PredictionFeatureSnapshot]],
    ) -> tuple[list[str], list[str], list[str]]:
        """Group by (target_type, target_id); assign whole groups by earliest cutoff."""
        groups: dict[tuple[str, str], list[DeliveryOutcome]] = defaultdict(list)
        for outcome, _ in rows:
            key = (
                outcome.target_type.value
                if hasattr(outcome.target_type, "value")
                else str(outcome.target_type),
                outcome.target_id,
            )
            groups[key].append(outcome)

        group_keys: list[tuple[datetime, str, str, str]] = []
        for (target_type, target_id), outcomes in groups.items():
            earliest = min(_aware(o.prediction_cutoff_at) for o in outcomes)
            first_outcome_id = sorted(o.delivery_outcome_id for o in outcomes)[0]
            group_keys.append((earliest, target_id, first_outcome_id, f"{target_type}|{target_id}"))

        group_keys.sort(key=lambda item: (item[0], item[1], item[2]))
        ordered_group_ids = [item[3] for item in group_keys]
        n = len(ordered_group_ids)
        if n == 0:
            return [], [], []

        train_end = int(n * TRAIN_FRACTION)
        cal_end = train_end + int(n * CALIBRATION_FRACTION)
        # Ensure remainder goes to test; avoid empty middle partitions when possible.
        if n >= 5:
            train_end = max(train_end, 1)
            cal_end = max(cal_end, train_end + 1)
            cal_end = min(cal_end, n - 1)

        train_groups = set(ordered_group_ids[:train_end])
        cal_groups = set(ordered_group_ids[train_end:cal_end])
        train_ids: list[str] = []
        cal_ids: list[str] = []
        test_ids: list[str] = []

        # Stable within-partition ordering by (cutoff, target_id, outcome_id).
        def sort_key(o: DeliveryOutcome) -> tuple[datetime, str, str]:
            return (_aware(o.prediction_cutoff_at), o.target_id, o.delivery_outcome_id)

        for (target_type, target_id), outcomes in groups.items():
            gid = f"{target_type}|{target_id}"
            ordered = sorted(outcomes, key=sort_key)
            ids = [o.delivery_outcome_id for o in ordered]
            if gid in train_groups:
                train_ids.extend(ids)
            elif gid in cal_groups:
                cal_ids.extend(ids)
            else:
                test_ids.extend(ids)

        train_ids.sort(
            key=lambda oid: next(sort_key(o) for o, _ in rows if o.delivery_outcome_id == oid)
        )
        cal_ids.sort(
            key=lambda oid: next(sort_key(o) for o, _ in rows if o.delivery_outcome_id == oid)
        )
        test_ids.sort(
            key=lambda oid: next(sort_key(o) for o, _ in rows if o.delivery_outcome_id == oid)
        )
        return train_ids, cal_ids, test_ids

    @staticmethod
    def _sufficiency_report(
        *,
        labeled_rows: int,
        positive_rows: int,
        negative_rows: int,
        calibration_rows: int,
        test_rows: int,
        leakage_clean: bool,
    ) -> dict[str, Any]:
        checks = {
            "min_labeled_rows": {
                "required": MIN_LABELED_ROWS,
                "actual": labeled_rows,
                "passed": labeled_rows >= MIN_LABELED_ROWS,
            },
            "min_positive_rows": {
                "required": MIN_POSITIVE_ROWS,
                "actual": positive_rows,
                "passed": positive_rows >= MIN_POSITIVE_ROWS,
            },
            "min_negative_rows": {
                "required": MIN_NEGATIVE_ROWS,
                "actual": negative_rows,
                "passed": negative_rows >= MIN_NEGATIVE_ROWS,
            },
            "min_calibration_rows": {
                "required": MIN_CALIBRATION_ROWS,
                "actual": calibration_rows,
                "passed": calibration_rows >= MIN_CALIBRATION_ROWS,
            },
            "min_test_rows": {
                "required": MIN_TEST_ROWS,
                "actual": test_rows,
                "passed": test_rows >= MIN_TEST_ROWS,
            },
            "leakage_clean": {
                "required": True,
                "actual": leakage_clean,
                "passed": leakage_clean,
            },
        }
        passed = all(item["passed"] for item in checks.values())
        missing = [name for name, item in checks.items() if not item["passed"]]
        return {"passed": passed, "checks": checks, "missing_requirements": missing}

    @staticmethod
    def _resolve_data_scope(
        rows: list[tuple[DeliveryOutcome, PredictionFeatureSnapshot]],
    ) -> PredictionDataScope:
        scopes = {o.data_scope for o, _ in rows}
        if not scopes or scopes == {PredictionDataScope.SYNTHETIC}:
            return PredictionDataScope.SYNTHETIC
        if PredictionDataScope.CUSTOMER_CONSENTED in scopes:
            return PredictionDataScope.CUSTOMER_CONSENTED
        if PredictionDataScope.PUBLIC in scopes:
            return PredictionDataScope.PUBLIC
        return PredictionDataScope.SYNTHETIC
