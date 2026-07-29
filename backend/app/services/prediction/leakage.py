"""Leakage validation for delivery prediction training rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.domain.prediction_constants import FORBIDDEN_FEATURE_TOKENS
from app.domain.prediction_models import FeatureLineageEntry, LeakageReport
from app.services.persistence.snapshot_service import snapshot_hash
from app.services.prediction.feature_schema import FEATURE_NAMES, get_feature_meta

_LEAKAGE_FEATURE_NAMES = frozenset(
    {
        "binary_label",
        "outcome_category",
        "actual_completed_at",
        "probability_of_delivery_success",
        "delivery_outcome_id",
        "observation_window_end_at",
    }
)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return _ensure_utc(parsed)
    return None


class PredictionLeakageValidator:
    """Reject training/backtest rows that use post-cutoff or outcome information."""

    def validate_row(
        self,
        row: Mapping[str, Any],
        *,
        prediction_cutoff_at: datetime | None = None,
    ) -> list[str]:
        reasons: list[str] = []
        cutoff = _ensure_utc(
            prediction_cutoff_at
            or _parse_dt(row.get("prediction_cutoff_at"))
            or _parse_dt(row.get("as_of_at"))
        )
        if cutoff is None:
            reasons.append("missing_prediction_cutoff")
            return reasons

        feature_values = row.get("feature_values") or {}
        if not isinstance(feature_values, Mapping):
            reasons.append("invalid_feature_values")
            feature_values = {}

        for name in feature_values:
            if name in _LEAKAGE_FEATURE_NAMES:
                reasons.append(f"outcome_label_in_features:{name}")
            lowered = str(name).lower()
            for token in FORBIDDEN_FEATURE_TOKENS:
                if token in lowered:
                    reasons.append(f"forbidden_feature:{name}")
                    break
            if "actual_completed" in lowered or "outcome_category" in lowered:
                reasons.append(f"outcome_field_in_features:{name}")

        evidence_cutoff = _parse_dt(row.get("evidence_cutoff_at"))
        if evidence_cutoff is not None and evidence_cutoff > cutoff:
            reasons.append("evidence_cutoff_after_prediction_cutoff")

        actual_completed = _parse_dt(row.get("actual_completed_at"))
        if actual_completed is not None and "actual_completed_at" in feature_values:
            reasons.append("actual_completed_at_in_features")
        if actual_completed is not None and actual_completed < cutoff:
            # Completion before cutoff is allowed as historical fact on the
            # outcome record, but must never appear as a feature value.
            pass

        for key in ("outcome_category", "binary_label"):
            if key in feature_values:
                reasons.append(f"outcome_label_in_features:{key}")

        lineage = row.get("feature_lineage") or row.get("lineage") or []
        latest_source: datetime | None = None
        if isinstance(lineage, Sequence):
            for entry in lineage:
                ts = self._lineage_timestamp(entry)
                if ts is None:
                    continue
                if latest_source is None or ts > latest_source:
                    latest_source = ts
                if ts > cutoff:
                    reasons.append("lineage_source_after_cutoff")

        source_timestamps = row.get("source_timestamps") or {}
        if isinstance(source_timestamps, Mapping):
            for key, raw in source_timestamps.items():
                ts = _parse_dt(raw)
                if ts is None:
                    continue
                if latest_source is None or ts > latest_source:
                    latest_source = ts
                if ts > cutoff:
                    reasons.append(f"source_timestamp_after_cutoff:{key}")

        for event_key in (
            "observed_at",
            "event_time",
            "detected_at",
            "edge_valid_from",
            "readiness_created_at",
            "resolved_at",
            "deployment_completed_at",
            "incident_resolved_at",
        ):
            ts = _parse_dt(row.get(event_key))
            if ts is not None and ts > cutoff:
                # resolved_at / completion after cutoff must not be used as features
                if event_key in {"resolved_at", "deployment_completed_at", "incident_resolved_at"}:
                    if event_key in feature_values or row.get("uses_post_cutoff_resolution"):
                        reasons.append(f"post_cutoff_{event_key}")
                else:
                    reasons.append(f"{event_key}_after_cutoff")

        if row.get("uses_current_graph_state"):
            reasons.append("current_graph_state_substituted")
        if row.get("uses_test_statistics_for_scaling"):
            reasons.append("test_statistics_used_for_scaling")
        if row.get("uses_test_statistics_for_imputation"):
            reasons.append("test_statistics_used_for_imputation")
        if row.get("calibrator_fit_on_test"):
            reasons.append("calibration_used_test_labels")

        # High leakage-risk features require explicit lineage timestamps <= cutoff.
        for name in feature_values:
            meta = get_feature_meta(str(name))
            if meta is None:
                continue
            if meta.leakage_risk == "high" and not self._has_lineage_for(lineage, str(name)):
                reasons.append(f"high_leakage_feature_without_lineage:{name}")

        return sorted(set(reasons))

    def validate_dataset(self, rows: Sequence[Mapping[str, Any]]) -> LeakageReport:
        rejection_reasons: dict[str, int] = {}
        suspicious: set[str] = set()
        latest_source: datetime | None = None
        cutoff_violations = 0
        rejected = 0

        for row in rows:
            reasons = self.validate_row(row)
            if reasons:
                rejected += 1
            for reason in reasons:
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                if "after_cutoff" in reason or reason.startswith("post_cutoff_"):
                    cutoff_violations += 1
                if reason.startswith("outcome_") or reason.startswith("forbidden_feature"):
                    for name in row.get("feature_values") or {}:
                        if name in _LEAKAGE_FEATURE_NAMES or any(
                            t in str(name).lower() for t in FORBIDDEN_FEATURE_TOKENS
                        ):
                            suspicious.add(str(name))

            lineage = row.get("feature_lineage") or row.get("lineage") or []
            if isinstance(lineage, Sequence):
                for entry in lineage:
                    ts = self._lineage_timestamp(entry)
                    if ts is not None and (latest_source is None or ts > latest_source):
                        latest_source = ts
            stamps = row.get("source_timestamps") or {}
            if isinstance(stamps, Mapping):
                for raw in stamps.values():
                    ts = _parse_dt(raw)
                    if ts is not None and (latest_source is None or ts > latest_source):
                        latest_source = ts

            for name in row.get("feature_values") or {}:
                if name not in FEATURE_NAMES:
                    suspicious.add(str(name))

        clean = rejected == 0
        payload = {
            "rows_examined": len(rows),
            "rows_rejected": rejected,
            "rejection_reasons": dict(sorted(rejection_reasons.items())),
            "suspicious_features": sorted(suspicious),
            "latest_source_timestamp": latest_source.isoformat() if latest_source else None,
            "cutoff_violations": cutoff_violations,
            "clean": clean,
        }
        return LeakageReport(
            rows_examined=len(rows),
            rows_rejected=rejected,
            rejection_reasons=dict(sorted(rejection_reasons.items())),
            suspicious_features=sorted(suspicious),
            latest_source_timestamp=latest_source,
            cutoff_violations=cutoff_violations,
            clean=clean,
            report_hash=snapshot_hash(payload),
        )

    @staticmethod
    def _lineage_timestamp(entry: Any) -> datetime | None:
        if isinstance(entry, FeatureLineageEntry):
            return _ensure_utc(entry.source_timestamp)
        if isinstance(entry, Mapping):
            return _parse_dt(entry.get("source_timestamp"))
        return None

    @staticmethod
    def _has_lineage_for(lineage: Any, feature_name: str) -> bool:
        if not isinstance(lineage, Sequence):
            return False
        for entry in lineage:
            if isinstance(entry, FeatureLineageEntry) and entry.feature_name == feature_name:
                return True
            if isinstance(entry, Mapping) and entry.get("feature_name") == feature_name:
                return True
        return False
