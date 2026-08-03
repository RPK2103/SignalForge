"""Data freshness and ingestion-lag calculations (Phase 3 Prompt 8).

Deterministic, timezone-aware definitions:

    ingestion lag  = ingestion_time - source_event_time
    freshness age  = evaluation_time - latest_valid_source_event_time

Edge cases are represented honestly (never fabricated):
- missing event time            -> status ``unavailable`` (age/lag = None);
- future event time             -> ``clock_skew`` (lag rejected);
- no successful checkpoint       -> status ``never_synced``;
- age within threshold          -> ``fresh``; else ``aging`` / ``stale``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    NEVER_SYNCED = "never_synced"
    UNAVAILABLE = "unavailable"


# Default per-source staleness thresholds (seconds). Aging = half of stale.
DEFAULT_STALE_THRESHOLDS: dict[str, int] = {
    "github": 24 * 3600,
    "azure_devops": 24 * 3600,
    "default": 48 * 3600,
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class IngestionLag:
    lag_seconds: float | None
    clock_skew: bool
    available: bool


def compute_ingestion_lag(
    *, source_event_time: datetime | None, ingestion_time: datetime | None
) -> IngestionLag:
    if source_event_time is None or ingestion_time is None:
        return IngestionLag(lag_seconds=None, clock_skew=False, available=False)
    event = _as_utc(source_event_time)
    ingested = _as_utc(ingestion_time)
    delta = (ingested - event).total_seconds()
    if delta < 0:
        # Negative lag => source clock ahead of ingestion clock; do not fabricate.
        return IngestionLag(lag_seconds=None, clock_skew=True, available=True)
    return IngestionLag(lag_seconds=delta, clock_skew=False, available=True)


@dataclass(frozen=True, slots=True)
class Freshness:
    status: FreshnessStatus
    age_seconds: float | None
    stale_threshold_seconds: int
    clock_skew: bool


def stale_threshold(source_type: str) -> int:
    return DEFAULT_STALE_THRESHOLDS.get(source_type, DEFAULT_STALE_THRESHOLDS["default"])


def compute_freshness(
    *,
    source_type: str,
    latest_source_event_time: datetime | None,
    evaluation_time: datetime | None = None,
    has_successful_checkpoint: bool = True,
) -> Freshness:
    threshold = stale_threshold(source_type)
    if not has_successful_checkpoint:
        return Freshness(FreshnessStatus.NEVER_SYNCED, None, threshold, False)
    if latest_source_event_time is None:
        return Freshness(FreshnessStatus.UNAVAILABLE, None, threshold, False)
    now = _as_utc(evaluation_time) if evaluation_time else datetime.now(timezone.utc)
    event = _as_utc(latest_source_event_time)
    age = (now - event).total_seconds()
    if age < 0:
        # Future event time: clock skew — report unavailable age rather than fake.
        return Freshness(FreshnessStatus.UNAVAILABLE, None, threshold, True)
    if age <= threshold / 2:
        status = FreshnessStatus.FRESH
    elif age <= threshold:
        status = FreshnessStatus.AGING
    else:
        status = FreshnessStatus.STALE
    return Freshness(status, age, threshold, False)
