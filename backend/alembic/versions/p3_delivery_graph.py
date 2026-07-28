"""delivery graph foundation

Revision ID: p3_delivery_graph
Revises: p3_connector_ingestion_foundation
Create Date: 2026-07-28 22:00:00.000000

Additive Phase 3 Prompt 3 migration:
- DeliveryGraphNode / DeliveryGraphEdge relational projections
- GraphProjectionRun / GraphAnalysisRun
- GraphFinding / GraphFindingEvidence
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.types

revision: str = "p3_delivery_graph"
down_revision: Union[str, Sequence[str], None] = "p3_connector_ingestion_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ent_delivery_graph_nodes",
        sa.Column("graph_node_id", sa.String(length=64), nullable=False),
        sa.Column("node_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_key", sa.String(length=256), nullable=False),
        sa.Column("display_label", sa.String(length=128), nullable=False),
        sa.Column("source_entity_version", sa.String(length=32), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("projection_version", sa.String(length=16), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("graph_node_id", name=op.f("pk_ent_delivery_graph_nodes")),
        sa.UniqueConstraint(
            "tenant_id", "node_type", "entity_id", name="uq_ent_delivery_graph_nodes_entity"
        ),
        sa.UniqueConstraint(
            "tenant_id", "canonical_key", name="uq_ent_delivery_graph_nodes_canonical"
        ),
    )
    op.create_index(
        op.f("ix_ent_delivery_graph_nodes_tenant_id"),
        "ent_delivery_graph_nodes",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_dgn_tenant_type", "ent_delivery_graph_nodes", ["tenant_id", "node_type"]
    )
    op.create_index(
        "ix_ent_dgn_tenant_entity", "ent_delivery_graph_nodes", ["tenant_id", "entity_id"]
    )
    op.create_index(
        "ix_ent_dgn_tenant_archived",
        "ent_delivery_graph_nodes",
        ["tenant_id", "archived_at"],
    )

    op.create_table(
        "ent_delivery_graph_edges",
        sa.Column("graph_edge_id", sa.String(length=64), nullable=False),
        sa.Column("source_node_id", sa.String(length=64), nullable=False),
        sa.Column("target_node_id", sa.String(length=64), nullable=False),
        sa.Column("edge_type", sa.String(length=32), nullable=False),
        sa.Column("edge_origin", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("criticality", sa.String(length=16), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supporting_evidence_signal_id", sa.String(length=64), nullable=True),
        sa.Column("supporting_ownership_id", sa.String(length=64), nullable=True),
        sa.Column("supporting_dependency_id", sa.String(length=64), nullable=True),
        sa.Column("derivation_rule", sa.String(length=128), nullable=True),
        sa.Column("derivation_version", sa.String(length=16), nullable=True),
        sa.Column("attributes", app.db.types.PortableJSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("projection_version", sa.String(length=16), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_node_id <> target_node_id", name="ck_ent_dge_no_self_edge"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_ent_dge_valid_interval",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_ent_dge_confidence_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"],
            ["ent_delivery_graph_nodes.graph_node_id"],
            name=op.f("fk_ent_delivery_graph_edges_source_node_id_ent_delivery_graph_nodes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["ent_delivery_graph_nodes.graph_node_id"],
            name=op.f("fk_ent_delivery_graph_edges_target_node_id_ent_delivery_graph_nodes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("graph_edge_id", name=op.f("pk_ent_delivery_graph_edges")),
        sa.UniqueConstraint(
            "tenant_id", "graph_edge_id", name="uq_ent_delivery_graph_edges_id_tenant"
        ),
    )
    op.create_index(
        op.f("ix_ent_delivery_graph_edges_tenant_id"),
        "ent_delivery_graph_edges",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_ent_delivery_graph_edges_source_node_id"),
        "ent_delivery_graph_edges",
        ["source_node_id"],
    )
    op.create_index(
        op.f("ix_ent_delivery_graph_edges_target_node_id"),
        "ent_delivery_graph_edges",
        ["target_node_id"],
    )
    op.create_index(
        "ix_ent_dge_tenant_source_type",
        "ent_delivery_graph_edges",
        ["tenant_id", "source_node_id", "edge_type"],
    )
    op.create_index(
        "ix_ent_dge_tenant_target_type",
        "ent_delivery_graph_edges",
        ["tenant_id", "target_node_id", "edge_type"],
    )
    op.create_index(
        "ix_ent_dge_tenant_valid",
        "ent_delivery_graph_edges",
        ["tenant_id", "valid_from", "valid_to"],
    )
    op.create_index(
        "ix_ent_dge_tenant_archived",
        "ent_delivery_graph_edges",
        ["tenant_id", "archived_at"],
    )
    op.create_index(
        "ix_ent_dge_tenant_origin",
        "ent_delivery_graph_edges",
        ["tenant_id", "edge_origin"],
    )
    op.create_index(
        "ix_ent_dge_tenant_projection",
        "ent_delivery_graph_edges",
        ["tenant_id", "projection_version"],
    )

    op.create_table(
        "ent_graph_projection_runs",
        sa.Column("graph_projection_run_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("projection_version", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nodes_examined", sa.Integer(), nullable=False),
        sa.Column("nodes_created", sa.Integer(), nullable=False),
        sa.Column("nodes_updated", sa.Integer(), nullable=False),
        sa.Column("nodes_archived", sa.Integer(), nullable=False),
        sa.Column("edges_examined", sa.Integer(), nullable=False),
        sa.Column("edges_created", sa.Integer(), nullable=False),
        sa.Column("edges_updated", sa.Integer(), nullable=False),
        sa.Column("edges_closed", sa.Integer(), nullable=False),
        sa.Column("errors", app.db.types.PortableJSON(), nullable=False),
        sa.Column("sanitized_error_summary", sa.String(length=1024), nullable=True),
        sa.Column("source_high_watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subject_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "nodes_examined >= 0 AND nodes_created >= 0 AND nodes_updated >= 0 "
            "AND nodes_archived >= 0 AND edges_examined >= 0 AND edges_created >= 0 "
            "AND edges_updated >= 0 AND edges_closed >= 0",
            name="ck_ent_gpr_nonneg_counters",
        ),
        sa.PrimaryKeyConstraint(
            "graph_projection_run_id", name=op.f("pk_ent_graph_projection_runs")
        ),
    )
    op.create_index(
        op.f("ix_ent_graph_projection_runs_tenant_id"),
        "ent_graph_projection_runs",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_gpr_tenant_state", "ent_graph_projection_runs", ["tenant_id", "state"]
    )
    op.create_index(
        "ix_ent_gpr_tenant_started",
        "ent_graph_projection_runs",
        ["tenant_id", "started_at"],
    )

    op.create_table(
        "ent_graph_analysis_runs",
        sa.Column("graph_analysis_run_id", sa.String(length=64), nullable=False),
        sa.Column("analysis_version", sa.String(length=16), nullable=False),
        sa.Column("graph_projection_version", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("findings_created", sa.Integer(), nullable=False),
        sa.Column("findings_resolved", sa.Integer(), nullable=False),
        sa.Column("findings_observed", sa.Integer(), nullable=False),
        sa.Column("sanitized_error_summary", sa.String(length=1024), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "findings_created >= 0 AND findings_resolved >= 0 AND findings_observed >= 0",
            name="ck_ent_gar_nonneg_counters",
        ),
        sa.PrimaryKeyConstraint(
            "graph_analysis_run_id", name=op.f("pk_ent_graph_analysis_runs")
        ),
    )
    op.create_index(
        op.f("ix_ent_graph_analysis_runs_tenant_id"),
        "ent_graph_analysis_runs",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ent_gar_tenant_state", "ent_graph_analysis_runs", ["tenant_id", "state"]
    )

    op.create_table(
        "ent_graph_findings",
        sa.Column("graph_finding_id", sa.String(length=64), nullable=False),
        sa.Column("finding_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("primary_node_id", sa.String(length=64), nullable=False),
        sa.Column("affected_node_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column("supporting_edge_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column(
            "supporting_evidence_signal_ids", app.db.types.PortableJSON(), nullable=False
        ),
        sa.Column("data_quality_warnings", app.db.types.PortableJSON(), nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("rule_version", sa.String(length=16), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finding_hash", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_ent_gf_confidence_bounds",
        ),
        sa.PrimaryKeyConstraint("graph_finding_id", name=op.f("pk_ent_graph_findings")),
    )
    op.create_index(
        op.f("ix_ent_graph_findings_tenant_id"), "ent_graph_findings", ["tenant_id"]
    )
    op.create_index(
        "ix_ent_gf_tenant_type_status",
        "ent_graph_findings",
        ["tenant_id", "finding_type", "status"],
    )
    op.create_index(
        "ix_ent_gf_tenant_primary",
        "ent_graph_findings",
        ["tenant_id", "primary_node_id"],
    )
    op.create_index(
        "ix_ent_gf_tenant_detected",
        "ent_graph_findings",
        ["tenant_id", "detected_at"],
    )
    op.create_index(
        "ix_ent_gf_tenant_hash_status",
        "ent_graph_findings",
        ["tenant_id", "finding_hash", "status"],
    )
    op.create_index(
        "uq_ent_gf_active_hash",
        "ent_graph_findings",
        ["tenant_id", "finding_hash"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "ent_graph_finding_evidence",
        sa.Column("graph_finding_evidence_id", sa.String(length=64), nullable=False),
        sa.Column("graph_finding_id", sa.String(length=64), nullable=False),
        sa.Column("evidence_kind", sa.String(length=32), nullable=False),
        sa.Column("evidence_ref_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["graph_finding_id"],
            ["ent_graph_findings.graph_finding_id"],
            name=op.f(
                "fk_ent_graph_finding_evidence_graph_finding_id_ent_graph_findings"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "graph_finding_evidence_id", name=op.f("pk_ent_graph_finding_evidence")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "graph_finding_id",
            "evidence_kind",
            "evidence_ref_id",
            name="uq_ent_gfe_unique",
        ),
    )
    op.create_index(
        op.f("ix_ent_graph_finding_evidence_tenant_id"),
        "ent_graph_finding_evidence",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_ent_graph_finding_evidence_graph_finding_id"),
        "ent_graph_finding_evidence",
        ["graph_finding_id"],
    )
    op.create_index(
        "ix_ent_gfe_tenant_finding",
        "ent_graph_finding_evidence",
        ["tenant_id", "graph_finding_id"],
    )


def downgrade() -> None:
    op.drop_table("ent_graph_finding_evidence")
    op.drop_index("uq_ent_gf_active_hash", table_name="ent_graph_findings")
    op.drop_table("ent_graph_findings")
    op.drop_table("ent_graph_analysis_runs")
    op.drop_table("ent_graph_projection_runs")
    op.drop_table("ent_delivery_graph_edges")
    op.drop_table("ent_delivery_graph_nodes")
