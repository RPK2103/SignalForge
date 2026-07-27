"""Audit event ORM model."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PortableJSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_aggregate", "aggregate_type", "aggregate_record_id"),
        Index("ix_audit_events_occurred_at", "occurred_at"),
    )

    audit_event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    event_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", PortableJSON, nullable=False, default=dict
    )
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
