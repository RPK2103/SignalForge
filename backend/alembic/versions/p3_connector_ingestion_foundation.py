"""connector ingestion foundation

Revision ID: p3_connector_ingestion_foundation
Revises: p3_enterprise_foundation
Create Date: 2026-07-28 18:00:00.000000

Additive Phase 3 Prompt 2 migration:
- Extends DataSource with validated non-secret connector_config and freshness.
- Extends IngestionRun with Prompt 2 counters.
- Extends Repository/WorkItem with projection provenance fields.
- Adds PullRequest, ConnectorCheckpoint, IngestionReceipt, IngestionDeadLetter.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

import app.db.types

revision: str = "p3_connector_ingestion_foundation"
down_revision: Union[str, Sequence[str], None] = "p3_enterprise_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- DataSource additive columns ---
    with op.batch_alter_table("ent_data_sources") as batch:
        batch.add_column(sa.Column("connector_config", app.db.types.PortableJSON(), nullable=True))
        batch.add_column(sa.Column("connector_config_schema_version", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("connector_config_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("last_attempted_sync_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_source_event_time", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_ingestion_time", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("freshness_state", sa.String(length=32), nullable=False, server_default="never_synced")
        )
        batch.add_column(
            sa.Column("stale_after_seconds", sa.Integer(), nullable=False, server_default="86400")
        )

    # --- IngestionRun additive counters ---
    with op.batch_alter_table("ent_ingestion_runs") as batch:
        batch.add_column(sa.Column("records_normalized", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("records_created", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("records_deduplicated", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("records_projected", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("records_dead_lettered", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("records_retried", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("rate_limit_waits", sa.Integer(), nullable=False, server_default="0"))

    # --- Repository / WorkItem projection provenance ---
    with op.batch_alter_table("ent_repositories") as batch:
        batch.add_column(sa.Column("last_evidence_signal_id", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column("source_precedence", sa.String(length=32), nullable=False, server_default="manual")
        )

    with op.batch_alter_table("ent_work_items") as batch:
        batch.add_column(sa.Column("title", sa.String(length=256), nullable=True))
        batch.add_column(sa.Column("last_evidence_signal_id", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column("source_precedence", sa.String(length=32), nullable=False, server_default="manual")
        )

    # --- PullRequest projection ---
    op.create_table(
        "ent_pull_requests",
        sa.Column("pull_request_id", sa.String(length=64), nullable=False),
        sa.Column("repository_id", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("draft", sa.Boolean(), nullable=False),
        sa.Column("author_external_id", sa.String(length=128), nullable=True),
        sa.Column("created_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("additions", sa.Integer(), nullable=True),
        sa.Column("deletions", sa.Integer(), nullable=True),
        sa.Column("changed_files", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_evidence_signal_id", sa.String(length=64), nullable=True),
        sa.Column("source_precedence", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "additions IS NULL OR (additions >= 0 AND additions <= 10000000)",
            name="pr_additions_bounds",
        ),
        sa.CheckConstraint(
            "deletions IS NULL OR (deletions >= 0 AND deletions <= 10000000)",
            name="pr_deletions_bounds",
        ),
        sa.CheckConstraint(
            "changed_files IS NULL OR (changed_files >= 0 AND changed_files <= 100000)",
            name="pr_changed_files_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["ent_repositories.repository_id"],
            name=op.f("fk_ent_pull_requests_repository_id_ent_repositories"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("pull_request_id", name=op.f("pk_ent_pull_requests")),
        sa.UniqueConstraint("tenant_id", "provider", "external_id", name="uq_ent_pull_requests_external"),
    )
    op.create_index(op.f("ix_ent_pull_requests_repository_id"), "ent_pull_requests", ["repository_id"])
    op.create_index(op.f("ix_ent_pull_requests_tenant_id"), "ent_pull_requests", ["tenant_id"])
    op.create_index("ix_ent_pull_requests_repo", "ent_pull_requests", ["tenant_id", "repository_id"])

    # --- ConnectorCheckpoint ---
    op.create_table(
        "ent_connector_checkpoints",
        sa.Column("connector_checkpoint_id", sa.String(length=64), nullable=False),
        sa.Column("data_source_id", sa.String(length=64), nullable=False),
        sa.Column("stream_name", sa.String(length=64), nullable=False),
        sa.Column("cursor_schema_version", sa.String(length=16), nullable=False),
        sa.Column("cursor_payload", app.db.types.PortableJSON(), nullable=False),
        sa.Column("cursor_hash", sa.String(length=64), nullable=False),
        sa.Column("high_watermark_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("high_watermark_source_id", sa.String(length=256), nullable=True),
        sa.Column("etag", sa.String(length=256), nullable=True),
        sa.Column("last_successful_run_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["ent_data_sources.data_source_id"],
            name=op.f("fk_ent_connector_checkpoints_data_source_id_ent_data_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("connector_checkpoint_id", name=op.f("pk_ent_connector_checkpoints")),
        sa.UniqueConstraint(
            "tenant_id",
            "data_source_id",
            "stream_name",
            name="uq_ent_connector_checkpoints_stream",
        ),
        sa.CheckConstraint("version >= 1", name="connector_checkpoint_version_positive"),
    )
    op.create_index(
        op.f("ix_ent_connector_checkpoints_data_source_id"),
        "ent_connector_checkpoints",
        ["data_source_id"],
    )
    op.create_index(
        op.f("ix_ent_connector_checkpoints_tenant_id"), "ent_connector_checkpoints", ["tenant_id"]
    )
    op.create_index(
        "ix_ent_connector_checkpoints_source",
        "ent_connector_checkpoints",
        ["tenant_id", "data_source_id"],
    )

    # --- IngestionReceipt ---
    op.create_table(
        "ent_ingestion_receipts",
        sa.Column("ingestion_receipt_id", sa.String(length=64), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=64), nullable=False),
        sa.Column("data_source_id", sa.String(length=64), nullable=False),
        sa.Column("stream_name", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.String(length=256), nullable=False),
        sa.Column("normalized_event_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_signal_id", sa.String(length=64), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("checkpoint_position", sa.String(length=512), nullable=True),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["ent_data_sources.data_source_id"],
            name=op.f("fk_ent_ingestion_receipts_data_source_id_ent_data_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ent_ingestion_runs.ingestion_run_id"],
            name=op.f("fk_ent_ingestion_receipts_ingestion_run_id_ent_ingestion_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ingestion_receipt_id", name=op.f("pk_ent_ingestion_receipts")),
        sa.UniqueConstraint(
            "tenant_id",
            "ingestion_run_id",
            "stream_name",
            "source_record_id",
            "payload_hash",
            name="uq_ent_ingestion_receipts_obs",
        ),
    )
    op.create_index(
        op.f("ix_ent_ingestion_receipts_data_source_id"), "ent_ingestion_receipts", ["data_source_id"]
    )
    op.create_index(
        op.f("ix_ent_ingestion_receipts_ingestion_run_id"),
        "ent_ingestion_receipts",
        ["ingestion_run_id"],
    )
    op.create_index(op.f("ix_ent_ingestion_receipts_tenant_id"), "ent_ingestion_receipts", ["tenant_id"])
    op.create_index(
        "ix_ent_ingestion_receipts_run", "ent_ingestion_receipts", ["tenant_id", "ingestion_run_id"]
    )
    op.create_index(
        "ix_ent_ingestion_receipts_source",
        "ent_ingestion_receipts",
        ["tenant_id", "data_source_id"],
    )

    # --- IngestionDeadLetter ---
    op.create_table(
        "ent_ingestion_dead_letters",
        sa.Column("dead_letter_id", sa.String(length=64), nullable=False),
        sa.Column("ingestion_run_id", sa.String(length=64), nullable=False),
        sa.Column("data_source_id", sa.String(length=64), nullable=False),
        sa.Column("stream_name", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.String(length=256), nullable=True),
        sa.Column("normalized_event_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("redacted_payload", app.db.types.PortableJSON(), nullable=False),
        sa.Column("error_category", sa.String(length=64), nullable=False),
        sa.Column("sanitized_error_summary", sa.String(length=1024), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("replay_state", sa.String(length=32), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["ent_data_sources.data_source_id"],
            name=op.f("fk_ent_ingestion_dead_letters_data_source_id_ent_data_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ent_ingestion_runs.ingestion_run_id"],
            name=op.f("fk_ent_ingestion_dead_letters_ingestion_run_id_ent_ingestion_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("dead_letter_id", name=op.f("pk_ent_ingestion_dead_letters")),
    )
    op.create_index(
        op.f("ix_ent_ingestion_dead_letters_data_source_id"),
        "ent_ingestion_dead_letters",
        ["data_source_id"],
    )
    op.create_index(
        op.f("ix_ent_ingestion_dead_letters_ingestion_run_id"),
        "ent_ingestion_dead_letters",
        ["ingestion_run_id"],
    )
    op.create_index(
        op.f("ix_ent_ingestion_dead_letters_tenant_id"), "ent_ingestion_dead_letters", ["tenant_id"]
    )
    op.create_index(
        "ix_ent_ingestion_dead_letters_run",
        "ent_ingestion_dead_letters",
        ["tenant_id", "ingestion_run_id"],
    )
    op.create_index(
        "ix_ent_ingestion_dead_letters_source",
        "ent_ingestion_dead_letters",
        ["tenant_id", "data_source_id"],
    )
    op.create_index(
        "ix_ent_ingestion_dead_letters_replay",
        "ent_ingestion_dead_letters",
        ["tenant_id", "replay_state"],
    )


def downgrade() -> None:
    op.drop_index("ix_ent_ingestion_dead_letters_replay", table_name="ent_ingestion_dead_letters")
    op.drop_index("ix_ent_ingestion_dead_letters_source", table_name="ent_ingestion_dead_letters")
    op.drop_index("ix_ent_ingestion_dead_letters_run", table_name="ent_ingestion_dead_letters")
    op.drop_index(op.f("ix_ent_ingestion_dead_letters_tenant_id"), table_name="ent_ingestion_dead_letters")
    op.drop_index(
        op.f("ix_ent_ingestion_dead_letters_ingestion_run_id"), table_name="ent_ingestion_dead_letters"
    )
    op.drop_index(
        op.f("ix_ent_ingestion_dead_letters_data_source_id"), table_name="ent_ingestion_dead_letters"
    )
    op.drop_table("ent_ingestion_dead_letters")

    op.drop_index("ix_ent_ingestion_receipts_source", table_name="ent_ingestion_receipts")
    op.drop_index("ix_ent_ingestion_receipts_run", table_name="ent_ingestion_receipts")
    op.drop_index(op.f("ix_ent_ingestion_receipts_tenant_id"), table_name="ent_ingestion_receipts")
    op.drop_index(
        op.f("ix_ent_ingestion_receipts_ingestion_run_id"), table_name="ent_ingestion_receipts"
    )
    op.drop_index(op.f("ix_ent_ingestion_receipts_data_source_id"), table_name="ent_ingestion_receipts")
    op.drop_table("ent_ingestion_receipts")

    op.drop_index("ix_ent_connector_checkpoints_source", table_name="ent_connector_checkpoints")
    op.drop_index(op.f("ix_ent_connector_checkpoints_tenant_id"), table_name="ent_connector_checkpoints")
    op.drop_index(
        op.f("ix_ent_connector_checkpoints_data_source_id"), table_name="ent_connector_checkpoints"
    )
    op.drop_table("ent_connector_checkpoints")

    op.drop_index("ix_ent_pull_requests_repo", table_name="ent_pull_requests")
    op.drop_index(op.f("ix_ent_pull_requests_tenant_id"), table_name="ent_pull_requests")
    op.drop_index(op.f("ix_ent_pull_requests_repository_id"), table_name="ent_pull_requests")
    op.drop_table("ent_pull_requests")

    with op.batch_alter_table("ent_work_items") as batch:
        batch.drop_column("source_precedence")
        batch.drop_column("last_evidence_signal_id")
        batch.drop_column("title")

    with op.batch_alter_table("ent_repositories") as batch:
        batch.drop_column("source_precedence")
        batch.drop_column("last_evidence_signal_id")

    with op.batch_alter_table("ent_ingestion_runs") as batch:
        batch.drop_column("rate_limit_waits")
        batch.drop_column("request_count")
        batch.drop_column("records_retried")
        batch.drop_column("records_dead_lettered")
        batch.drop_column("records_projected")
        batch.drop_column("records_deduplicated")
        batch.drop_column("records_created")
        batch.drop_column("records_normalized")

    with op.batch_alter_table("ent_data_sources") as batch:
        batch.drop_column("stale_after_seconds")
        batch.drop_column("freshness_state")
        batch.drop_column("last_ingestion_time")
        batch.drop_column("last_source_event_time")
        batch.drop_column("last_successful_sync_at")
        batch.drop_column("last_attempted_sync_at")
        batch.drop_column("connector_config_hash")
        batch.drop_column("connector_config_schema_version")
        batch.drop_column("connector_config")
