"""Human review ORM model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.assessment import Assessment


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HumanReview(Base):
    __tablename__ = "human_reviews"
    __table_args__ = (Index("ix_human_reviews_assessment_record_id", "assessment_record_id"),)

    review_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    assessment_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assessments.assessment_record_id"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")

    assessment: Mapped["Assessment"] = relationship(back_populates="reviews")
