"""Simulation ORM model."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PortableJSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Simulation(Base):
    __tablename__ = "simulations"
    __table_args__ = (
        Index("ix_simulations_simulation_id", "simulation_id"),
        Index("ix_simulations_project_id", "project_id"),
        Index("ix_simulations_created_at", "created_at"),
    )

    simulation_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    simulation_id: Mapped[str] = mapped_column(String(16), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id"), nullable=False
    )
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    input_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_snapshot: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    baseline_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_snapshot: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    proposed_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_snapshot: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    result_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    readiness_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    actor_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
