"""continuous recon: scheduled jobs and asset change events

Revision ID: 99b4d6b4ad01
Revises: 392e4638a4d8
Create Date: 2026-08-12 09:37:00.059339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '99b4d6b4ad01'
down_revision: Union[str, None] = '392e4638a4d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=True),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("profile", sa.String(length=64), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "PAUSED", "DISABLED", name="scheduled_job_status"),
            nullable=False,
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_job_id", sa.UUID(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Read by the ticker on every tick (app/scheduling/ticker.py) to find due
    # schedules -- WHERE status = 'ACTIVE' AND next_run_at <= now().
    op.create_index("ix_scheduled_jobs_status_next_run_at", "scheduled_jobs", ["status", "next_run_at"])
    op.create_index("ix_scheduled_jobs_asset_id", "scheduled_jobs", ["asset_id"])

    op.create_table(
        "asset_change_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("previous_job_id", sa.UUID(), nullable=True),
        sa.Column(
            "change_type",
            sa.Enum(
                "PORT_OPENED",
                "PORT_CLOSED",
                "SERVICE_CHANGED",
                "TECHNOLOGY_ADDED",
                "TECHNOLOGY_REMOVED",
                "TECHNOLOGY_CHANGED",
                "CERTIFICATE_CHANGED",
                "HTTP_CHANGED",
                "OTHER",
                name="asset_change_type",
            ),
            nullable=False,
        ),
        sa.Column("field", sa.String(length=256), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("change_metadata", sa.JSON(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["previous_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Reuses the finding_severity enum type created by the Phase 9 migration
    # (Finding.severity) -- added via raw SQL rather than sa.Enum(...) in the
    # column list above, because SQLAlchemy's DDL-event machinery insists on
    # attempting CREATE TYPE for any Enum object attached to a new table
    # (even with create_type=False) when the type is shared across tables in
    # the same MetaData, causing a DuplicateObject error against the already
    # -existing type.
    op.execute("ALTER TABLE asset_change_events ADD COLUMN severity finding_severity NOT NULL")
    # Read by the Asset detail page's Change Timeline -- most-recent-first,
    # scoped to one asset.
    op.create_index("ix_asset_change_events_asset_id_detected_at", "asset_change_events", ["asset_id", "detected_at"])


def downgrade() -> None:
    op.drop_index("ix_asset_change_events_asset_id_detected_at", table_name="asset_change_events")
    op.drop_table("asset_change_events")
    sa.Enum(name="asset_change_type").drop(op.get_bind())
    # finding_severity is NOT dropped -- owned by the Phase 9 migration
    # (Finding.severity), still in use there after this downgrade.

    op.drop_index("ix_scheduled_jobs_asset_id", table_name="scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_status_next_run_at", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
    sa.Enum(name="scheduled_job_status").drop(op.get_bind())
