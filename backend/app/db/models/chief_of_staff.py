"""AI Chief of Staff ORM models (Phase 3 Prompt 6).

Evidence snapshots, runs, briefs, claims, citations, and append-only reviews.
Briefs/claims/citations are immutable after creation. Regeneration creates a new run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PortableJSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _CosTenantBase(Base):
    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class CosEvidenceSnapshot(_CosTenantBase):
    __tablename__ = "ent_cos_evidence_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "package_hash", name="uq_ent_cos_snap_tenant_hash"),
        Index(
            "ix_ent_cos_snap_tenant_target_asof",
            "tenant_id",
            "target_type",
            "target_id",
            "as_of_at",
        ),
        Index("ix_ent_cos_snap_tenant_hash", "tenant_id", "package_hash"),
        CheckConstraint(
            "horizon_days IS NULL OR horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_cos_snap_horizon",
        ),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    package_json: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    truncation_flags: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)


class CosRun(_CosTenantBase):
    __tablename__ = "ent_cos_runs"
    __table_args__ = (
        Index(
            "ix_ent_cos_run_tenant_target_asof",
            "tenant_id",
            "target_type",
            "target_id",
            "as_of_at",
        ),
        Index(
            "ix_ent_cos_run_tenant_state_created",
            "tenant_id",
            "generation_state",
            "created_at",
        ),
        Index("ix_ent_cos_run_tenant_intent", "tenant_id", "intent"),
        Index("ix_ent_cos_run_tenant_prior_brief", "tenant_id", "prior_brief_id"),
        CheckConstraint(
            "horizon_days IS NULL OR horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_cos_run_horizon",
        ),
        CheckConstraint(
            "generation_state IN ('generated', 'fallback_generated', 'rejected', 'failed')",
            name="ck_ent_cos_run_state",
        ),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_snapshot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_cos_evidence_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    prior_brief_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    final_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_deployment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fallback_template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_state: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grounding_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    citation_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)


class CosBrief(_CosTenantBase):
    __tablename__ = "ent_cos_briefs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", name="uq_ent_cos_brief_tenant_run"),
        Index(
            "ix_ent_cos_brief_tenant_target_asof",
            "tenant_id",
            "target_type",
            "target_id",
            "as_of_at",
        ),
        Index("ix_ent_cos_brief_tenant_created", "tenant_id", "created_at"),
        Index("ix_ent_cos_brief_tenant_hash", "tenant_id", "output_hash"),
        CheckConstraint(
            "horizon_days IS NULL OR horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_cos_brief_horizon",
        ),
        CheckConstraint(
            "generation_state IN ('generated', 'fallback_generated', 'rejected', 'failed')",
            name="ck_ent_cos_brief_state",
        ),
    )

    brief_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_cos_runs.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_snapshot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_cos_evidence_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brief_json: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_state: Mapped[str] = mapped_column(String(32), nullable=False)
    final_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    estimate_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)


class CosClaim(_CosTenantBase):
    __tablename__ = "ent_cos_claims"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "brief_id",
            "ordering_index",
            name="uq_ent_cos_claim_brief_order",
        ),
        Index("ix_ent_cos_claim_tenant_brief", "tenant_id", "brief_id"),
        CheckConstraint("ordering_index >= 0", name="ck_ent_cos_claim_order"),
    )

    # Persisted as "{brief_id}:{logical_claim_id}" (≤128).
    claim_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    brief_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_cos_briefs.brief_id", ondelete="RESTRICT"),
        nullable=False,
    )
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    support_status: Mapped[str] = mapped_column(String(32), nullable=False)
    authorship: Mapped[str] = mapped_column(String(32), nullable=False)
    temporal_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(PortableJSON(), nullable=False)
    semantic_metadata: Mapped[dict] = mapped_column(PortableJSON(), nullable=False)
    ordering_index: Mapped[int] = mapped_column(Integer, nullable=False)


class CosCitation(_CosTenantBase):
    __tablename__ = "ent_cos_citations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "claim_id",
            "evidence_id",
            name="uq_ent_cos_citation_claim_evidence",
        ),
        UniqueConstraint(
            "tenant_id",
            "claim_id",
            "ordering_index",
            name="uq_ent_cos_citation_claim_order",
        ),
        Index("ix_ent_cos_citation_tenant_brief", "tenant_id", "brief_id"),
        CheckConstraint("ordering_index >= 0", name="ck_ent_cos_citation_order"),
    )

    # Persisted as "{brief_id}:{logical_citation_id}" (≤128).
    citation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    brief_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_cos_briefs.brief_id", ondelete="RESTRICT"),
        nullable=False,
    )
    claim_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("ent_cos_claims.claim_id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    package_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_cos_evidence_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    ordering_index: Mapped[int] = mapped_column(Integer, nullable=False)


class CosReview(_CosTenantBase):
    __tablename__ = "ent_cos_reviews"
    __table_args__ = (
        Index(
            "ix_ent_cos_review_tenant_brief_created",
            "tenant_id",
            "brief_id",
            "created_at",
        ),
        CheckConstraint(
            "review_state IN ('accepted', 'needs_revision', 'rejected', 'needs_more_evidence')",
            name="ck_ent_cos_review_state",
        ),
    )

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    brief_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_cos_briefs.brief_id", ondelete="RESTRICT"),
        nullable=False,
    )
    review_state: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_context: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
