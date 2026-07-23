"""leadership_briefs schema

Revision ID: a1b2c3d4e5f6
Revises: d573b27e3974
Create Date: 2026-07-24 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d573b27e3974"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leadership_briefs",
        sa.Column("leadership_brief_record_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_record_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.String(length=16), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("provider_mode", sa.String(length=32), nullable=False),
        sa.Column("generation_status", sa.String(length=32), nullable=False),
        sa.Column("failure_category", sa.String(length=64), nullable=True),
        sa.Column("evidence_package_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_package_hash", sa.String(length=64), nullable=False),
        sa.Column("output_snapshot", sa.JSON(), nullable=False),
        sa.Column("output_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_record_id"],
            ["assessments.assessment_record_id"],
            name=op.f("fk_leadership_briefs_assessment_record_id_assessments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "leadership_brief_record_id",
            name=op.f("pk_leadership_briefs"),
        ),
    )
    op.create_index(
        "ix_leadership_briefs_assessment_record_id",
        "leadership_briefs",
        ["assessment_record_id"],
        unique=False,
    )
    op.create_index(
        "ix_leadership_briefs_created_at",
        "leadership_briefs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_leadership_briefs_provider_mode",
        "leadership_briefs",
        ["provider_mode"],
        unique=False,
    )
    op.create_index(
        "ix_leadership_briefs_generation_status",
        "leadership_briefs",
        ["generation_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_leadership_briefs_generation_status", table_name="leadership_briefs")
    op.drop_index("ix_leadership_briefs_provider_mode", table_name="leadership_briefs")
    op.drop_index("ix_leadership_briefs_created_at", table_name="leadership_briefs")
    op.drop_index("ix_leadership_briefs_assessment_record_id", table_name="leadership_briefs")
    op.drop_table("leadership_briefs")
