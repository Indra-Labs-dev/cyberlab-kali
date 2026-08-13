"""phase 21 mission templates and chain runs

Revision ID: c3e7a9f2d5b8
Revises: b2d5f8a1c6e3
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e7a9f2d5b8'
down_revision: Union[str, None] = 'b2d5f8a1c6e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mission_templates",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "mission_template_steps",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("mission_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("profile", sa.String(length=64), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "condition_type",
            sa.Enum("ALWAYS", "PORT_OPEN", "TECHNOLOGY_DETECTED", "MIN_SEVERITY", name="chain_condition_type"),
            nullable=False,
            server_default="ALWAYS",
        ),
        sa.Column("condition_params", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("template_id", "step_order", name="uq_mission_template_step_order"),
    )
    op.create_index("ix_mission_template_steps_template_id", "mission_template_steps", ["template_id"])

    op.create_table(
        "chain_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("mission_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("RUNNING", "COMPLETED", "FAILED", "CANCELLED", name="chain_run_status"),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_chain_runs_target_id", "chain_runs", ["target_id"])
    op.create_index("ix_chain_runs_status", "chain_runs", ["status"])

    op.create_table(
        "chain_run_steps",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chain_run_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("chain_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("profile", sa.String(length=64), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "condition_type",
            sa.Enum("ALWAYS", "PORT_OPEN", "TECHNOLOGY_DETECTED", "MIN_SEVERITY", name="chain_condition_type"),
            nullable=False,
            server_default="ALWAYS",
        ),
        sa.Column("condition_params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SKIPPED", "QUEUED", "SUCCESS", "FAILED", "CANCELLED", name="chain_run_step_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("chain_run_id", "step_order", name="uq_chain_run_step_order"),
        sa.CheckConstraint(
            "status NOT IN ('QUEUED', 'SUCCESS', 'FAILED') OR job_id IS NOT NULL",
            name="ck_chain_run_step_job_id_required_when_executed",
        ),
    )
    op.create_index("ix_chain_run_steps_chain_run_id", "chain_run_steps", ["chain_run_id"])
    op.create_index("ix_chain_run_steps_job_id", "chain_run_steps", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_chain_run_steps_job_id", table_name="chain_run_steps")
    op.drop_index("ix_chain_run_steps_chain_run_id", table_name="chain_run_steps")
    op.drop_table("chain_run_steps")

    op.drop_index("ix_chain_runs_status", table_name="chain_runs")
    op.drop_index("ix_chain_runs_target_id", table_name="chain_runs")
    op.drop_table("chain_runs")

    op.drop_index("ix_mission_template_steps_template_id", table_name="mission_template_steps")
    op.drop_table("mission_template_steps")

    op.drop_table("mission_templates")

    sa.Enum(name="chain_run_step_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="chain_run_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="chain_condition_type").drop(op.get_bind(), checkfirst=True)
