"""continuous scenario intelligence

Revision ID: p3_continuous_scenario_intelligence
Revises: p3_delivery_prediction
Create Date: 2026-07-29 12:00:00.000000

Additive Phase 3 Prompt 5 migration:
- ScenarioDefinition / ScenarioVersion
- ScenarioWatch / ScenarioTriggerEvent
- ScenarioRun / ScenarioFeatureOverlay
- ScenarioResult / ScenarioImpact
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.types

revision: str = "p3_continuous_scenario_intelligence"
down_revision: Union[str, Sequence[str], None] = "p3_delivery_prediction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ent_scenario_definitions",
        sa.Column("scenario_definition_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_kind", sa.String(length=64), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_version >= 0", name="ck_ent_scen_def_version_nonneg"),
        sa.PrimaryKeyConstraint("scenario_definition_id", name=op.f("pk_ent_scenario_definitions")),
        sa.UniqueConstraint("tenant_id", "name", name="uq_ent_scen_def_tenant_name"),
    )
    op.create_index(
        "ix_ent_scen_def_tenant_target",
        "ent_scenario_definitions",
        ["tenant_id", "target_type", "target_id"],
    )
    op.create_index(
        "ix_ent_scen_def_tenant_kind",
        "ent_scenario_definitions",
        ["tenant_id", "scenario_kind"],
    )
    op.create_index(
        "ix_ent_scen_def_tenant_lifecycle",
        "ent_scenario_definitions",
        ["tenant_id", "lifecycle_state"],
    )
    op.create_index(
        op.f("ix_ent_scenario_definitions_tenant_id"),
        "ent_scenario_definitions",
        ["tenant_id"],
    )

    op.create_table(
        "ent_scenario_versions",
        sa.Column("scenario_version_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_definition_id", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("scenario_schema_version", sa.String(length=64), nullable=False),
        sa.Column("assumptions", app.db.types.PortableJSON(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_context", sa.String(length=64), nullable=False),
        sa.Column("specification_hash", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_number >= 1", name="ck_ent_scen_ver_number"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_ent_scen_ver_interval",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_definition_id"],
            ["ent_scenario_definitions.scenario_definition_id"],
            name=op.f("fk_ent_scenario_versions_scenario_definition_id_ent_scenario_definitions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("scenario_version_id", name=op.f("pk_ent_scenario_versions")),
        sa.UniqueConstraint(
            "tenant_id",
            "scenario_definition_id",
            "version_number",
            name="uq_ent_scen_ver_def_version",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "specification_hash",
            name="uq_ent_scen_ver_spec_hash",
        ),
    )
    op.create_index(
        "ix_ent_scen_ver_tenant_def",
        "ent_scenario_versions",
        ["tenant_id", "scenario_definition_id"],
    )
    op.create_index(
        "ix_ent_scen_ver_tenant_hash",
        "ent_scenario_versions",
        ["tenant_id", "specification_hash"],
    )
    op.create_index(
        op.f("ix_ent_scenario_versions_tenant_id"),
        "ent_scenario_versions",
        ["tenant_id"],
    )

    op.create_table(
        "ent_scenario_watches",
        sa.Column("scenario_watch_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_definition_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_version_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("watch_mode", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False),
        sa.Column("minimum_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_eligible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("last_scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("last_result_hash", sa.String(length=64), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "minimum_interval_minutes >= 60",
            name="ck_ent_scen_watch_interval",
        ),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_ent_scen_watch_failures"),
        sa.CheckConstraint("lock_version >= 0", name="ck_ent_scen_watch_lock"),
        sa.ForeignKeyConstraint(
            ["scenario_definition_id"],
            ["ent_scenario_definitions.scenario_definition_id"],
            name=op.f("fk_ent_scenario_watches_scenario_definition_id_ent_scenario_definitions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_version_id"],
            ["ent_scenario_versions.scenario_version_id"],
            name=op.f("fk_ent_scenario_watches_scenario_version_id_ent_scenario_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("scenario_watch_id", name=op.f("pk_ent_scenario_watches")),
        sa.UniqueConstraint(
            "tenant_id",
            "scenario_version_id",
            "target_type",
            "target_id",
            name="uq_ent_scen_watch_version_target",
        ),
    )
    op.create_index(
        "ix_ent_scen_watch_tenant_lifecycle",
        "ent_scenario_watches",
        ["tenant_id", "lifecycle_state"],
    )
    op.create_index(
        "ix_ent_scen_watch_tenant_next",
        "ent_scenario_watches",
        ["tenant_id", "next_eligible_at"],
    )
    op.create_index(
        "ix_ent_scen_watch_tenant_fp",
        "ent_scenario_watches",
        ["tenant_id", "last_source_fingerprint"],
    )
    op.create_index(
        op.f("ix_ent_scenario_watches_tenant_id"),
        "ent_scenario_watches",
        ["tenant_id"],
    )

    op.create_table(
        "ent_scenario_runs",
        sa.Column("scenario_run_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_version_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_definition_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("run_mode", sa.String(length=32), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("baseline_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("scenario_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("run_input_hash", sa.String(length=64), nullable=False),
        sa.Column("graph_projection_version", sa.String(length=16), nullable=True),
        sa.Column("prediction_model_id", sa.String(length=64), nullable=True),
        sa.Column("prediction_baseline_version", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nodes_examined", sa.Integer(), nullable=False),
        sa.Column("edges_examined", sa.Integer(), nullable=False),
        sa.Column("impacts_created", sa.Integer(), nullable=False),
        sa.Column("sanitized_error_summary", sa.String(length=512), nullable=True),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_scen_run_horizon",
        ),
        sa.CheckConstraint("nodes_examined >= 0", name="ck_ent_scen_run_nodes"),
        sa.CheckConstraint("edges_examined >= 0", name="ck_ent_scen_run_edges"),
        sa.CheckConstraint("impacts_created >= 0", name="ck_ent_scen_run_impacts"),
        sa.ForeignKeyConstraint(
            ["scenario_definition_id"],
            ["ent_scenario_definitions.scenario_definition_id"],
            name=op.f("fk_ent_scenario_runs_scenario_definition_id_ent_scenario_definitions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_version_id"],
            ["ent_scenario_versions.scenario_version_id"],
            name=op.f("fk_ent_scenario_runs_scenario_version_id_ent_scenario_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("scenario_run_id", name=op.f("pk_ent_scenario_runs")),
        sa.UniqueConstraint(
            "tenant_id",
            "run_input_hash",
            name="uq_ent_scen_run_input_hash",
        ),
    )
    op.create_index(
        "ix_ent_scen_run_tenant_version",
        "ent_scenario_runs",
        ["tenant_id", "scenario_version_id"],
    )
    op.create_index(
        "ix_ent_scen_run_tenant_target",
        "ent_scenario_runs",
        ["tenant_id", "target_type", "target_id"],
    )
    op.create_index(
        "ix_ent_scen_run_tenant_state",
        "ent_scenario_runs",
        ["tenant_id", "state"],
    )
    op.create_index(
        "ix_ent_scen_run_tenant_asof",
        "ent_scenario_runs",
        ["tenant_id", "as_of_at"],
    )
    op.create_index(
        "ix_ent_scen_run_tenant_fp",
        "ent_scenario_runs",
        ["tenant_id", "source_fingerprint"],
    )
    op.create_index(
        op.f("ix_ent_scenario_runs_tenant_id"),
        "ent_scenario_runs",
        ["tenant_id"],
    )

    op.create_table(
        "ent_scenario_trigger_events",
        sa.Column("scenario_trigger_event_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_watch_id", sa.String(length=64), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger_reason", sa.String(length=64), nullable=False),
        sa.Column("previous_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("current_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("changed_components", app.db.types.PortableJSON(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("sanitized_error_summary", sa.String(length=512), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["scenario_watch_id"],
            ["ent_scenario_watches.scenario_watch_id"],
            name=op.f("fk_ent_scenario_trigger_events_scenario_watch_id_ent_scenario_watches"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "scenario_trigger_event_id", name=op.f("pk_ent_scenario_trigger_events")
        ),
    )
    op.create_index(
        "ix_ent_scen_trig_tenant_watch",
        "ent_scenario_trigger_events",
        ["tenant_id", "scenario_watch_id"],
    )
    op.create_index(
        "ix_ent_scen_trig_tenant_detected",
        "ent_scenario_trigger_events",
        ["tenant_id", "detected_at"],
    )
    op.create_index(
        "ix_ent_scen_trig_tenant_action",
        "ent_scenario_trigger_events",
        ["tenant_id", "action"],
    )
    op.create_index(
        op.f("ix_ent_scenario_trigger_events_tenant_id"),
        "ent_scenario_trigger_events",
        ["tenant_id"],
    )

    op.create_table(
        "ent_scenario_feature_overlays",
        sa.Column("scenario_feature_overlay_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=False),
        sa.Column("baseline_feature_snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False),
        sa.Column("overlay_schema_version", sa.String(length=64), nullable=False),
        sa.Column("baseline_values_hash", sa.String(length=64), nullable=False),
        sa.Column("changed_feature_values", app.db.types.PortableJSON(), nullable=False),
        sa.Column("simulated_feature_values", app.db.types.PortableJSON(), nullable=False),
        sa.Column("feature_delta", app.db.types.PortableJSON(), nullable=False),
        sa.Column("feature_lineage", app.db.types.PortableJSON(), nullable=False),
        sa.Column("simulation_origin", sa.String(length=32), nullable=False),
        sa.Column(
            "training_eligible",
            sa.Boolean(),
            nullable=False,
            # Dialect-safe Boolean default: renders ``0`` on SQLite and ``false``
            # on PostgreSQL. A numeric ``sa.text("0")`` default is rejected by
            # PostgreSQL for a Boolean column.
            server_default=sa.false(),
        ),
        sa.Column("overlay_hash", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            # Dialect-safe boolean predicate (see delivery-prediction migration).
            "NOT training_eligible",
            name="ck_ent_scen_overlay_not_training",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_run_id"],
            ["ent_scenario_runs.scenario_run_id"],
            name=op.f("fk_ent_scenario_feature_overlays_scenario_run_id_ent_scenario_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "scenario_feature_overlay_id", name=op.f("pk_ent_scenario_feature_overlays")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "scenario_run_id",
            name="uq_ent_scen_overlay_run",
        ),
    )
    op.create_index(
        "ix_ent_scen_overlay_tenant_run",
        "ent_scenario_feature_overlays",
        ["tenant_id", "scenario_run_id"],
    )
    op.create_index(
        "ix_ent_scen_overlay_tenant_hash",
        "ent_scenario_feature_overlays",
        ["tenant_id", "overlay_hash"],
    )
    op.create_index(
        op.f("ix_ent_scenario_feature_overlays_tenant_id"),
        "ent_scenario_feature_overlays",
        ["tenant_id"],
    )

    op.create_table(
        "ent_scenario_results",
        sa.Column("scenario_result_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("scenario_kind", sa.String(length=64), nullable=False),
        sa.Column("baseline_summary", app.db.types.PortableJSON(), nullable=False),
        sa.Column("simulated_summary", app.db.types.PortableJSON(), nullable=False),
        sa.Column("delta_summary", app.db.types.PortableJSON(), nullable=False),
        sa.Column("baseline_estimate_kind", sa.String(length=32), nullable=False),
        sa.Column("simulated_estimate_kind", sa.String(length=32), nullable=False),
        sa.Column("estimate_comparability", sa.String(length=64), nullable=False),
        sa.Column("baseline_probability", sa.Float(), nullable=True),
        sa.Column("simulated_probability", sa.Float(), nullable=True),
        sa.Column("probability_delta", sa.Float(), nullable=True),
        sa.Column("baseline_risk_score", sa.Float(), nullable=True),
        sa.Column("simulated_risk_score", sa.Float(), nullable=True),
        sa.Column("risk_score_delta", sa.Float(), nullable=True),
        sa.Column("baseline_risk_band", sa.String(length=32), nullable=True),
        sa.Column("simulated_risk_band", sa.String(length=32), nullable=True),
        sa.Column("affected_project_count", sa.Integer(), nullable=False),
        sa.Column("affected_initiative_count", sa.Integer(), nullable=False),
        sa.Column("affected_critical_initiative_count", sa.Integer(), nullable=False),
        sa.Column("findings_added_count", sa.Integer(), nullable=False),
        sa.Column("findings_removed_count", sa.Integer(), nullable=False),
        sa.Column("findings_worsened_count", sa.Integer(), nullable=False),
        sa.Column("findings_improved_count", sa.Integer(), nullable=False),
        sa.Column("data_quality_warnings", app.db.types.PortableJSON(), nullable=False),
        sa.Column("applicability_warnings", app.db.types.PortableJSON(), nullable=False),
        sa.Column("assumption_summary", app.db.types.PortableJSON(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "horizon_days IN (30, 60, 90, 180)",
            name="ck_ent_scen_result_horizon",
        ),
        sa.CheckConstraint("affected_project_count >= 0", name="ck_ent_scen_result_proj"),
        sa.CheckConstraint("affected_initiative_count >= 0", name="ck_ent_scen_result_init"),
        sa.CheckConstraint(
            "affected_critical_initiative_count >= 0", name="ck_ent_scen_result_crit"
        ),
        sa.CheckConstraint("findings_added_count >= 0", name="ck_ent_scen_result_fadd"),
        sa.CheckConstraint("findings_removed_count >= 0", name="ck_ent_scen_result_frem"),
        sa.CheckConstraint("findings_worsened_count >= 0", name="ck_ent_scen_result_fworse"),
        sa.CheckConstraint("findings_improved_count >= 0", name="ck_ent_scen_result_fimp"),
        sa.CheckConstraint(
            "baseline_probability IS NULL OR "
            "(baseline_probability >= 0 AND baseline_probability <= 1)",
            name="ck_ent_scen_result_bprob",
        ),
        sa.CheckConstraint(
            "simulated_probability IS NULL OR "
            "(simulated_probability >= 0 AND simulated_probability <= 1)",
            name="ck_ent_scen_result_sprob",
        ),
        sa.CheckConstraint(
            "baseline_risk_score IS NULL OR "
            "(baseline_risk_score >= 0 AND baseline_risk_score <= 100)",
            name="ck_ent_scen_result_bscore",
        ),
        sa.CheckConstraint(
            "simulated_risk_score IS NULL OR "
            "(simulated_risk_score >= 0 AND simulated_risk_score <= 100)",
            name="ck_ent_scen_result_sscore",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_run_id"],
            ["ent_scenario_runs.scenario_run_id"],
            name=op.f("fk_ent_scenario_results_scenario_run_id_ent_scenario_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("scenario_result_id", name=op.f("pk_ent_scenario_results")),
        sa.UniqueConstraint(
            "tenant_id",
            "scenario_run_id",
            name="uq_ent_scen_result_run",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "result_hash",
            name="uq_ent_scen_result_hash",
        ),
    )
    op.create_index(
        "ix_ent_scen_result_tenant_run",
        "ent_scenario_results",
        ["tenant_id", "scenario_run_id"],
    )
    op.create_index(
        "ix_ent_scen_result_tenant_target",
        "ent_scenario_results",
        ["tenant_id", "target_type", "target_id"],
    )
    op.create_index(
        op.f("ix_ent_scenario_results_tenant_id"),
        "ent_scenario_results",
        ["tenant_id"],
    )

    op.create_table(
        "ent_scenario_impacts",
        sa.Column("scenario_impact_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=False),
        sa.Column("impact_type", sa.String(length=64), nullable=False),
        sa.Column("primary_node_id", sa.String(length=64), nullable=True),
        sa.Column("affected_node_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column("supporting_edge_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column(
            "supporting_evidence_signal_ids",
            app.db.types.PortableJSON(),
            nullable=False,
        ),
        sa.Column("assumption_ids", app.db.types.PortableJSON(), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.String(length=512), nullable=False),
        sa.Column("impact_hash", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["scenario_run_id"],
            ["ent_scenario_runs.scenario_run_id"],
            name=op.f("fk_ent_scenario_impacts_scenario_run_id_ent_scenario_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("scenario_impact_id", name=op.f("pk_ent_scenario_impacts")),
        sa.UniqueConstraint(
            "tenant_id",
            "impact_hash",
            name="uq_ent_scen_impact_hash",
        ),
    )
    op.create_index(
        "ix_ent_scen_impact_tenant_run",
        "ent_scenario_impacts",
        ["tenant_id", "scenario_run_id"],
    )
    op.create_index(
        "ix_ent_scen_impact_tenant_type",
        "ent_scenario_impacts",
        ["tenant_id", "impact_type"],
    )
    op.create_index(
        op.f("ix_ent_scenario_impacts_tenant_id"),
        "ent_scenario_impacts",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_table("ent_scenario_impacts")
    op.drop_table("ent_scenario_results")
    op.drop_table("ent_scenario_feature_overlays")
    op.drop_table("ent_scenario_trigger_events")
    op.drop_table("ent_scenario_runs")
    op.drop_table("ent_scenario_watches")
    op.drop_table("ent_scenario_versions")
    op.drop_table("ent_scenario_definitions")
