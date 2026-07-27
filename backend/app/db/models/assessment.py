"""Assessment ORM models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import PortableJSON

if TYPE_CHECKING:
    from app.db.models.review import HumanReview


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        Index("ix_assessments_assessment_id", "assessment_id"),
        Index("ix_assessments_project_id", "project_id"),
        Index("ix_assessments_created_at", "created_at"),
    )

    assessment_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(16), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id"), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    input_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_snapshot: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    result_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    actor_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")

    risk_findings: Mapped[list["AssessmentRiskFinding"]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
    decision_traces: Mapped[list["AssessmentDecisionTrace"]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[list["HumanReview"]] = relationship(
        back_populates="assessment",
    )


class AssessmentRiskFinding(Base):
    __tablename__ = "assessment_risk_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assessments.assessment_record_id"),
        nullable=False,
        index=True,
    )
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    capability_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engineer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    assessment: Mapped["Assessment"] = relationship(back_populates="risk_findings")


class AssessmentDecisionTrace(Base):
    __tablename__ = "assessment_decision_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assessments.assessment_record_id"),
        nullable=False,
        index=True,
    )
    step: Mapped[str] = mapped_column(String(32), nullable=False)
    component: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    contribution: Mapped[float] = mapped_column(Float, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    assessment: Mapped["Assessment"] = relationship(back_populates="decision_traces")
