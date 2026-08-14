"""phase 23 indexes on jobs, findings, assets

Revision ID: e5f1a9c7d3b2
Revises: d4f6b1e8c9a7
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e5f1a9c7d3b2'
down_revision: Union[str, None] = 'd4f6b1e8c9a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # jobs: the single most-referenced table in the schema (7 other tables
    # FK into it) had zero secondary indexes despite project_id/target_id/
    # status/created_at all being routine filter/sort columns.
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])
    op.create_index("ix_jobs_target_id", "jobs", ["target_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])

    # findings.job_id: joined/filtered constantly (report building, risk
    # recalculation, the Asset detail page) with no supporting index.
    op.create_index("ix_findings_job_id", "findings", ["job_id"])

    # assets.project_id: filtered/joined constantly (project scoping on
    # nearly every Asset query, AI Memory, the Security Graph) with no
    # supporting index. Table name in the DB is "assets" (Phase 13
    # generalized "targets" -> "assets"), matching app/models/asset.py.
    op.create_index("ix_assets_project_id", "assets", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_assets_project_id", table_name="assets")
    op.drop_index("ix_findings_job_id", table_name="findings")
    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_target_id", table_name="jobs")
    op.drop_index("ix_jobs_project_id", table_name="jobs")
