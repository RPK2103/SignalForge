"""Data freshness policy — versioned thresholds, not calibrated."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.enterprise_enums import FreshnessState

FRESHNESS_POLICY_VERSION = "1"


def compute_freshness(
    *,
    last_successful_sync_at: datetime | None,
    last_attempted_sync_at: datetime | None,
    failed: bool,
    stale_after_seconds: int,
    now: datetime | None = None,
) -> FreshnessState:
    """Bounded freshness states. Not calibrated for SLA decisions."""
    current = now or datetime.now(timezone.utc)
    if failed and last_successful_sync_at is None:
        return FreshnessState.FAILED
    if last_successful_sync_at is None and last_attempted_sync_at is None:
        return FreshnessState.NEVER_SYNCED
    if last_successful_sync_at is None:
        return FreshnessState.FAILED
    age = (current - last_successful_sync_at).total_seconds()
    if age <= stale_after_seconds * 0.5:
        return FreshnessState.FRESH
    if age <= stale_after_seconds:
        return FreshnessState.AGING
    return FreshnessState.STALE


def aging_threshold(stale_after_seconds: int) -> timedelta:
    return timedelta(seconds=stale_after_seconds * 0.5)
