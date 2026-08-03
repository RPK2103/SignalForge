"""Data freshness + ingestion-lag tests (Phase 3 Prompt 8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.observability.freshness import (
    FreshnessStatus,
    compute_freshness,
    compute_ingestion_lag,
)

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_ingestion_lag_positive():
    lag = compute_ingestion_lag(source_event_time=NOW - timedelta(seconds=30), ingestion_time=NOW)
    assert lag.available and lag.lag_seconds == 30.0 and not lag.clock_skew


def test_ingestion_lag_missing_event_time():
    lag = compute_ingestion_lag(source_event_time=None, ingestion_time=NOW)
    assert not lag.available and lag.lag_seconds is None


def test_ingestion_lag_clock_skew():
    lag = compute_ingestion_lag(source_event_time=NOW + timedelta(seconds=30), ingestion_time=NOW)
    assert lag.clock_skew and lag.lag_seconds is None


def test_fresh_evidence():
    result = compute_freshness(
        source_type="github",
        latest_source_event_time=NOW - timedelta(hours=1),
        evaluation_time=NOW,
    )
    assert result.status is FreshnessStatus.FRESH
    assert result.age_seconds == 3600.0


def test_stale_evidence():
    result = compute_freshness(
        source_type="github",
        latest_source_event_time=NOW - timedelta(days=3),
        evaluation_time=NOW,
    )
    assert result.status is FreshnessStatus.STALE


def test_missing_event_time_unavailable():
    result = compute_freshness(
        source_type="github", latest_source_event_time=None, evaluation_time=NOW
    )
    assert result.status is FreshnessStatus.UNAVAILABLE
    assert result.age_seconds is None


def test_future_event_time_not_fabricated():
    result = compute_freshness(
        source_type="github",
        latest_source_event_time=NOW + timedelta(days=1),
        evaluation_time=NOW,
    )
    assert result.status is FreshnessStatus.UNAVAILABLE
    assert result.clock_skew and result.age_seconds is None


def test_no_checkpoint_never_synced():
    result = compute_freshness(
        source_type="github",
        latest_source_event_time=None,
        evaluation_time=NOW,
        has_successful_checkpoint=False,
    )
    assert result.status is FreshnessStatus.NEVER_SYNCED
