"""Internal alert-state evaluation helpers (Phase 3 Prompt 8).

This is *internal state evaluation only* — no email, Teams, PagerDuty or SMS
delivery. A stable fingerprint deduplicates alerts so the same condition/window
never opens a second alert; state transitions are append-only and tenant-scoped
(enforced by the repository + RLS).
"""

from __future__ import annotations

import hashlib

from app.domain.observability_models import AlertSeverity, SloStatus


def alert_fingerprint(*, source: str, reason_code: str, subject: str) -> str:
    """Deterministic, low-cardinality fingerprint for deduplication.

    ``subject`` is a bounded internal key (e.g. an SLO key or run key). It is
    hashed so no raw identifier is stored as a plaintext dedup key.
    """
    raw = f"{source}|{reason_code}|{subject}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def severity_for_slo_status(status: SloStatus) -> AlertSeverity | None:
    if status is SloStatus.BREACHED:
        return AlertSeverity.CRITICAL
    if status is SloStatus.AT_RISK:
        return AlertSeverity.WARNING
    return None
