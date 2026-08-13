"""phase 19 project ai summaries

Revision ID: a1c4e6f9b3d2
Revises: f8721b028a2d
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c4e6f9b3d2'
down_revision: Union[str, None] = 'f8721b028a2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_ai_summaries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("based_on_job_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        # No separate index on project_id: the UniqueConstraint below
        # already creates one (a single-column unique constraint IS the
        # lookup index) -- unlike AICorrelationSuggestion's composite
        # unique constraint (Phase 18), which needed an extra single-column
        # index alongside it.
        sa.UniqueConstraint("project_id", name="uq_project_ai_summary_project"),
    )


def downgrade() -> None:
    op.drop_table("project_ai_summaries")
