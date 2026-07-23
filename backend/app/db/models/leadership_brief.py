"""Leadership Brief ORM model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PortableJSON


class LeadershipBrief(Base):
    __tablename__ = "leadership_briefs"

    leadership_brief_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True
    )
    assessment_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assessments.assessment_record_id", ondelete="RESTRICT"),
        nullable=False,
    )
    assessment_id: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    generation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_package_snapshot: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    evidence_package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_snapshot: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    output_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_leadership_briefs_assessment_record_id", "assessment_record_id"),
        Index("ix_leadership_briefs_created_at", "created_at"),
        Index("ix_leadership_briefs_provider_mode", "provider_mode"),
        Index("ix_leadership_briefs_generation_status", "generation_status"),
    )
