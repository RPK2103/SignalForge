"""Delivery Graph ORM models (Phase 3 Prompt 3).

Relational materialized projections. Source enterprise/connector tables remain
authoritative. Graph rows are tenant-scoped rebuildable projections.
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
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import PortableJSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _GraphTenantBase(Base):
    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class DeliveryGraphNode(_GraphTenantBase):
    __tablename__ = "ent_delivery_graph_nodes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "node_type",
            "entity_id",
            name="uq_ent_delivery_graph_nodes_entity",
        ),
        UniqueConstraint(
            "tenant_id",
            "canonical_key",
            name="uq_ent_delivery_graph_nodes_canonical",
        ),
        Index("ix_ent_dgn_tenant_type", "tenant_id", "node_type"),
        Index("ix_ent_dgn_tenant_entity", "tenant_id", "entity_id"),
        Index("ix_ent_dgn_tenant_archived", "tenant_id", "archived_at"),
    )

    graph_node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(256), nullable=False)
    display_label: Mapped[str] = mapped_column(String(128), nullable=False)
    source_entity_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    projection_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")


class DeliveryGraphEdge(_GraphTenantBase):
    __tablename__ = "ent_delivery_graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "graph_edge_id",
            name="uq_ent_delivery_graph_edges_id_tenant",
        ),
        CheckConstraint("source_node_id <> target_node_id", name="ck_ent_dge_no_self_edge"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_ent_dge_valid_interval",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_ent_dge_confidence_bounds",
        ),
        Index("ix_ent_dge_tenant_source_type", "tenant_id", "source_node_id", "edge_type"),
        Index("ix_ent_dge_tenant_target_type", "tenant_id", "target_node_id", "edge_type"),
        Index("ix_ent_dge_tenant_valid", "tenant_id", "valid_from", "valid_to"),
        Index("ix_ent_dge_tenant_archived", "tenant_id", "archived_at"),
        Index("ix_ent_dge_tenant_origin", "tenant_id", "edge_origin"),
        Index("ix_ent_dge_tenant_projection", "tenant_id", "projection_version"),
    )

    graph_edge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_node_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_delivery_graph_nodes.graph_node_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_delivery_graph_nodes.graph_node_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    edge_origin: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supporting_evidence_signal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supporting_ownership_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supporting_dependency_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    derivation_rule: Mapped[str | None] = mapped_column(String(128), nullable=True)
    derivation_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attributes: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    projection_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GraphProjectionRun(_GraphTenantBase):
    __tablename__ = "ent_graph_projection_runs"
    __table_args__ = (
        Index("ix_ent_gpr_tenant_state", "tenant_id", "state"),
        Index("ix_ent_gpr_tenant_started", "tenant_id", "started_at"),
        CheckConstraint(
            "nodes_examined >= 0 AND nodes_created >= 0 AND nodes_updated >= 0 "
            "AND nodes_archived >= 0 AND edges_examined >= 0 AND edges_created >= 0 "
            "AND edges_updated >= 0 AND edges_closed >= 0",
            name="ck_ent_gpr_nonneg_counters",
        ),
    )

    graph_projection_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    projection_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nodes_examined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nodes_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nodes_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nodes_archived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edges_examined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edges_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edges_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edges_closed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)
    sanitized_error_summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_high_watermark: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subject_ids: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)


class GraphAnalysisRun(_GraphTenantBase):
    __tablename__ = "ent_graph_analysis_runs"
    __table_args__ = (
        Index("ix_ent_gar_tenant_state", "tenant_id", "state"),
        CheckConstraint(
            "findings_created >= 0 AND findings_resolved >= 0 AND findings_observed >= 0",
            name="ck_ent_gar_nonneg_counters",
        ),
    )

    graph_analysis_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    graph_projection_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    findings_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_observed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sanitized_error_summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class GraphFinding(_GraphTenantBase):
    __tablename__ = "ent_graph_findings"
    __table_args__ = (
        Index("ix_ent_gf_tenant_type_status", "tenant_id", "finding_type", "status"),
        Index("ix_ent_gf_tenant_primary", "tenant_id", "primary_node_id"),
        Index("ix_ent_gf_tenant_detected", "tenant_id", "detected_at"),
        Index("ix_ent_gf_tenant_hash_status", "tenant_id", "finding_hash", "status"),
        Index(
            "uq_ent_gf_active_hash",
            "tenant_id",
            "finding_hash",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_ent_gf_confidence_bounds",
        ),
    )

    graph_finding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    primary_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    affected_node_ids: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)
    supporting_edge_ids: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)
    supporting_evidence_signal_ids: Mapped[list] = mapped_column(
        PortableJSON, nullable=False, default=list
    )
    data_quality_warnings: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finding_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class GraphFindingEvidence(_GraphTenantBase):
    __tablename__ = "ent_graph_finding_evidence"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "graph_finding_id",
            "evidence_kind",
            "evidence_ref_id",
            name="uq_ent_gfe_unique",
        ),
        Index("ix_ent_gfe_tenant_finding", "tenant_id", "graph_finding_id"),
    )

    graph_finding_evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    graph_finding_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ent_graph_findings.graph_finding_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
