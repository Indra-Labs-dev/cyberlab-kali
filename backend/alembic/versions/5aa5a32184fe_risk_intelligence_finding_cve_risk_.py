"""risk intelligence: finding cve/risk fields, vulnerability intel tables

Revision ID: 5aa5a32184fe
Revises: 99b4d6b4ad01
Create Date: 2026-08-12 10:34:14.453651

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5aa5a32184fe'
down_revision: Union[str, None] = '99b4d6b4ad01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Finding: CVE extraction + materialized Risk Score cache ---
    op.add_column("findings", sa.Column("cve_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.alter_column("findings", "cve_ids", server_default=None)
    op.add_column("findings", sa.Column("cvss_score", sa.Float(), nullable=True))
    op.add_column("findings", sa.Column("epss_score", sa.Float(), nullable=True))
    op.add_column("findings", sa.Column("kev", sa.Boolean(), nullable=True))
    op.add_column("findings", sa.Column("risk_score", sa.Integer(), nullable=True))
    risk_priority_enum = sa.Enum("INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL", name="risk_priority")
    risk_priority_enum.create(op.get_bind())
    op.add_column("findings", sa.Column("risk_priority", risk_priority_enum, nullable=True))
    op.add_column("findings", sa.Column("risk_calculated_at", sa.DateTime(timezone=True), nullable=True))
    # Read by GET /api/findings when sorting/filtering by risk (Phase 15).
    op.create_index("ix_findings_risk_score", "findings", ["risk_score"])
    op.create_index("ix_findings_kev", "findings", ["kev"])

    # --- vulnerability_intel: one row per CVE actually encountered ---
    op.create_table(
        "vulnerability_intel",
        sa.Column("cve", sa.String(length=32), nullable=False),
        sa.Column("cvss_score", sa.Float(), nullable=True),
        sa.Column("cvss_version", sa.String(length=8), nullable=True),
        sa.Column("cvss_vector", sa.String(length=128), nullable=True),
        sa.Column("cvss_source", sa.String(length=32), nullable=True),
        sa.Column("cvss_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("epss_score", sa.Float(), nullable=True),
        sa.Column("epss_percentile", sa.Float(), nullable=True),
        sa.Column("epss_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("cve"),
    )

    # --- cisa_kev_entries: full small catalog, refreshed wholesale ---
    op.create_table(
        "cisa_kev_entries",
        sa.Column("cve_id", sa.String(length=32), nullable=False),
        sa.Column("vendor_project", sa.String(length=256), nullable=True),
        sa.Column("product", sa.String(length=256), nullable=True),
        sa.Column("vulnerability_name", sa.String(length=512), nullable=True),
        sa.Column("date_added", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("known_ransomware_campaign_use", sa.Boolean(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("cve_id"),
    )

    # --- intel_sync_state: one row per source, tracks sync health ---
    op.create_table(
        "intel_sync_state",
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("source"),
    )


def downgrade() -> None:
    op.drop_table("intel_sync_state")
    op.drop_table("cisa_kev_entries")
    op.drop_table("vulnerability_intel")

    op.drop_index("ix_findings_kev", table_name="findings")
    op.drop_index("ix_findings_risk_score", table_name="findings")
    op.drop_column("findings", "risk_calculated_at")
    op.drop_column("findings", "risk_priority")
    sa.Enum(name="risk_priority").drop(op.get_bind())
    op.drop_column("findings", "risk_score")
    op.drop_column("findings", "kev")
    op.drop_column("findings", "epss_score")
    op.drop_column("findings", "cvss_score")
    op.drop_column("findings", "cve_ids")
