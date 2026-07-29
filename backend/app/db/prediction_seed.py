"""Deterministic NovaBank synthetic delivery-outcome seed (Phase 3 Prompt 4).

Labels are generated from a hash of (target_id, cutoff) plus mild noise — NOT from
scorecard rules — so training metrics are imperfect and realistic for demo.

Idempotent: a second run creates zero duplicate rows (deterministic PKs via
``build_entity_id`` / ``_ensure``).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.enterprise_seed import INITIATIVES, PROJECTS, TENANT_ID, _ensure, _tid
from app.db.models import prediction as pred_orm
from app.domain.prediction_constants import DEFAULT_HORIZON_DAYS, LABEL_VERSION, TARGET_DEFINITION
from app.domain.prediction_enums import (
    OutcomeCategory,
    PredictionDataScope,
    PredictionTargetType,
    VerificationStatus,
)

# Fixed epoch for ~2 years of historical cutoffs (independent of enterprise _BASE).
_EPOCH = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_HORIZON = DEFAULT_HORIZON_DAYS  # 90

# Project cutoffs: 8 dates × 8 projects = 64
_PROJECT_CUTOFF_DAYS = (0, 60, 120, 180, 240, 300, 360, 420)
# Initiative cutoffs (offset): 8 dates × 5 initiatives = 40 → total 104
_INITIATIVE_CUTOFF_DAYS = (30, 90, 150, 210, 270, 330, 390, 450)

_NOTES = (
    "Synthetic NovaBank delivery outcome for demo training only. "
    f"label_version={LABEL_VERSION}; data_scope=synthetic."
)


def _hash_int(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _synthetic_label(
    target_id: str, cutoff: datetime
) -> tuple[int | None, OutcomeCategory, VerificationStatus, str]:
    """Separate from scorecard rules — hash-driven with mild class noise (~55/45)."""
    seed = f"{target_id}|{cutoff.isoformat()}|synth_label_v1"
    primary = _hash_int(seed)
    secondary = _hash_int(seed, "noise")
    bucket = primary % 100

    # ~10% censored / excluded / pending (target ~8–12 of 104)
    if bucket < 5:
        return None, OutcomeCategory.CENSORED, VerificationStatus.EXCLUDED, "censored_window"
    if bucket < 8:
        return None, OutcomeCategory.UNKNOWN, VerificationStatus.PENDING, "pending_verification"
    if bucket < 10:
        return None, OutcomeCategory.CENSORED, VerificationStatus.EXCLUDED, "excluded_incomplete"

    # Labeled rows: ~55% positive / ~45% negative among remaining
    labeled_bucket = secondary % 100
    # Mild noise flip (~6%) so metrics are not perfect
    flip = (_hash_int(seed, "flip") % 100) < 6

    if labeled_bucket < 55:
        label = 0 if flip else 1
    else:
        label = 1 if flip else 0

    if label == 1:
        category = (
            OutcomeCategory.ON_TIME_SUCCESS
            if (secondary % 10) < 7
            else OutcomeCategory.DELAYED_SUCCESS
        )
    else:
        category = OutcomeCategory.FAILED if (secondary % 10) < 7 else OutcomeCategory.CANCELLED
    return label, category, VerificationStatus.VERIFIED, "verified_synthetic"


def _completion_times(
    *,
    cutoff: datetime,
    due_at: datetime,
    window_end: datetime,
    label: int | None,
    category: OutcomeCategory,
    noise: int,
) -> tuple[datetime | None, datetime | None]:
    """Return (actual_completed_at, finalized_at)."""
    if category in {OutcomeCategory.CENSORED, OutcomeCategory.UNKNOWN}:
        return None, None

    finalized = window_end
    if label == 1 and category == OutcomeCategory.ON_TIME_SUCCESS:
        # Complete before due, within horizon
        delta = timedelta(days=max(7, (due_at - cutoff).days - 5 - (noise % 10)))
        completed = cutoff + delta
        if completed > due_at:
            completed = due_at - timedelta(days=1)
        if completed < cutoff:
            completed = cutoff + timedelta(days=14)
        return completed, finalized

    if label == 1 and category == OutcomeCategory.DELAYED_SUCCESS:
        # After due but before observation window end
        mid = due_at + timedelta(days=5 + (noise % 15))
        if mid > window_end:
            mid = window_end - timedelta(hours=12)
        if mid < cutoff:
            mid = cutoff + timedelta(days=70)
        return mid, finalized

    if category == OutcomeCategory.FAILED:
        # Missed delivery — either never completed or completed after window
        if noise % 2 == 0:
            return None, finalized
        return window_end + timedelta(days=5 + (noise % 20)), finalized

    # Cancelled — no completion
    return None, finalized


def _seed_one(
    session: Session,
    *,
    target_type: PredictionTargetType,
    target_id: str,
    slug: str,
    cutoff: datetime,
) -> int:
    horizon = _HORIZON
    noise = _hash_int(target_id, cutoff.isoformat(), "due")
    due_offset = 60 + (noise % 31)  # 60–90 days
    due_at = cutoff + timedelta(days=due_offset)
    window_end = cutoff + timedelta(days=horizon)

    label, category, verification, reason = _synthetic_label(target_id, cutoff)
    completed_at, finalized_at = _completion_times(
        cutoff=cutoff,
        due_at=due_at,
        window_end=window_end,
        label=label,
        category=category,
        noise=noise,
    )

    outcome_id = _tid(
        "dout",
        target_type.value,
        target_id,
        cutoff.isoformat(),
        str(horizon),
        LABEL_VERSION,
    )
    notes = f"{_NOTES} target={slug}; reason={reason}."[:512]

    return _ensure(
        session,
        pred_orm.DeliveryOutcome,
        outcome_id,
        {
            "delivery_outcome_id": outcome_id,
            "target_type": target_type.value,
            "target_id": target_id,
            "outcome_definition": TARGET_DEFINITION,
            "label_version": LABEL_VERSION,
            "horizon_days": horizon,
            "prediction_cutoff_at": cutoff,
            "target_due_at": due_at,
            "observation_window_end_at": window_end,
            "actual_completed_at": completed_at,
            "outcome_category": category.value,
            "binary_label": label,
            "verification_status": verification.value,
            "verification_source": "synthetic_seed",
            "supporting_evidence_signal_ids": [],
            "source_snapshot_id": None,
            "notes_summary": notes,
            "data_scope": PredictionDataScope.SYNTHETIC.value,
            "finalized_at": finalized_at,
        },
    )


def seed_prediction_history(session: Session) -> dict[str, int]:
    """Idempotently seed NovaBank synthetic DeliveryOutcome rows.

    Returns counts suitable for merging into enterprise seed summary.
    """
    created = 0
    labeled = 0
    positive = 0
    negative = 0
    censored_or_excluded = 0

    for _name, slug, _init_slug, _team in PROJECTS:
        target_id = _tid("proj", slug)
        for day in _PROJECT_CUTOFF_DAYS:
            cutoff = _EPOCH + timedelta(days=day)
            n = _seed_one(
                session,
                target_type=PredictionTargetType.PROJECT,
                target_id=target_id,
                slug=slug,
                cutoff=cutoff,
            )
            created += n

    for _name, slug, _prio, _crit in INITIATIVES:
        target_id = _tid("init", slug)
        for day in _INITIATIVE_CUTOFF_DAYS:
            cutoff = _EPOCH + timedelta(days=day)
            n = _seed_one(
                session,
                target_type=PredictionTargetType.INITIATIVE,
                target_id=target_id,
                slug=slug,
                cutoff=cutoff,
            )
            created += n

    # Recount categories for summary (idempotent reporting of inventory)
    from sqlalchemy import func, select

    rows = session.execute(
        select(
            pred_orm.DeliveryOutcome.binary_label,
            pred_orm.DeliveryOutcome.outcome_category,
            pred_orm.DeliveryOutcome.verification_status,
            func.count(),
        )
        .where(pred_orm.DeliveryOutcome.tenant_id == TENANT_ID)
        .group_by(
            pred_orm.DeliveryOutcome.binary_label,
            pred_orm.DeliveryOutcome.outcome_category,
            pred_orm.DeliveryOutcome.verification_status,
        )
    ).all()
    for binary_label, category, verification, count in rows:
        count_i = int(count)
        if verification == VerificationStatus.VERIFIED.value and binary_label in (0, 1):
            labeled += count_i
            if binary_label == 1:
                positive += count_i
            else:
                negative += count_i
        else:
            censored_or_excluded += count_i

    return {
        "delivery_outcomes": created,
        "delivery_outcomes_labeled": labeled,
        "delivery_outcomes_positive": positive,
        "delivery_outcomes_negative": negative,
        "delivery_outcomes_censored_or_excluded": censored_or_excluded,
        "delivery_outcomes_total": labeled + censored_or_excluded,
    }
