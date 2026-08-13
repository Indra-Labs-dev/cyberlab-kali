"""phase 18 missions and ai correlation suggestions

Revision ID: f8721b028a2d
Revises: 496b351d1744
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8721b028a2d'
down_revision: Union[str, None] = '496b351d1744'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "APPROVED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", name="mission_status"),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("max_steps", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("max_steps > 0", name="ck_mission_max_steps_positive"),
    )
    op.create_index("ix_missions_target_id", "missions", ["target_id"])
    op.create_index("ix_missions_status", "missions", ["status"])

    op.create_table(
        "mission_steps",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mission_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=True),
        sa.Column("profile", sa.String(length=64), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SKIPPED", "QUEUED", "SUCCESS", "FAILED", "CANCELLED", name="mission_step_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("mission_id", "step_order", name="uq_mission_step_order"),
        sa.CheckConstraint(
            "status NOT IN ('QUEUED', 'SUCCESS', 'FAILED') OR job_id IS NOT NULL",
            name="ck_mission_step_job_id_required_when_executed",
        ),
    )
    op.create_index("ix_mission_steps_mission_id", "mission_steps", ["mission_id"])
    op.create_index("ix_mission_steps_job_id", "mission_steps", ["job_id"])

    op.create_table(
        "ai_correlation_suggestions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("finding_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("related_finding_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACCEPTED", "DISMISSED", name="ai_suggestion_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("finding_id != related_finding_id", name="ck_ai_suggestion_distinct_findings"),
        sa.UniqueConstraint("finding_id", "related_finding_id", name="uq_ai_suggestion_pair"),
    )
    op.create_index("ix_ai_suggestions_finding_id", "ai_correlation_suggestions", ["finding_id"])
    op.create_index("ix_ai_suggestions_status", "ai_correlation_suggestions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ai_suggestions_status", table_name="ai_correlation_suggestions")
    op.drop_index("ix_ai_suggestions_finding_id", table_name="ai_correlation_suggestions")
    op.drop_table("ai_correlation_suggestions")

    op.drop_index("ix_mission_steps_job_id", table_name="mission_steps")
    op.drop_index("ix_mission_steps_mission_id", table_name="mission_steps")
    op.drop_table("mission_steps")

    op.drop_index("ix_missions_status", table_name="missions")
    op.drop_index("ix_missions_target_id", table_name="missions")
    op.drop_table("missions")

    sa.Enum(name="ai_suggestion_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="mission_step_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="mission_status").drop(op.get_bind(), checkfirst=True)
