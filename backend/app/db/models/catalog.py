"""Catalog ORM models."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import PortableJSON
from app.domain.tenant_context import LEGACY_TENANT_ID


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Capability(Base):
    __tablename__ = "capabilities"

    capability_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Phase 3 compatibility: nullable tenant column backfilled to the legacy
    # tenant. Kept nullable so Phase 2 write paths remain non-breaking.
    tenant_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=LEGACY_TENANT_ID, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Engineer(Base):
    __tablename__ = "engineers"

    engineer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=LEGACY_TENANT_ID, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    experience_years: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    has_certifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    has_project_history: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    capabilities: Mapped[list["EngineerCapability"]] = relationship(
        back_populates="engineer",
        cascade="all, delete-orphan",
    )


class EngineerCapability(Base):
    __tablename__ = "engineer_capabilities"
    __table_args__ = (
        UniqueConstraint("engineer_id", "capability_id", name="uq_engineer_capability"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engineer_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("engineers.engineer_id"), nullable=False, index=True
    )
    capability_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capabilities.capability_id"), nullable=False, index=True
    )
    proficiency: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_sources: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    engineer: Mapped["Engineer"] = relationship(back_populates="capabilities")


class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=LEGACY_TENANT_ID, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    requirements: Mapped[list["ProjectRequirement"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class ProjectRequirement(Base):
    __tablename__ = "project_requirements"
    __table_args__ = (
        UniqueConstraint("project_id", "capability_id", name="uq_project_capability"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id"), nullable=False, index=True
    )
    capability_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capabilities.capability_id"), nullable=False, index=True
    )
    required_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped["Project"] = relationship(back_populates="requirements")
