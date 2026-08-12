"""correlation deduplication and finding lifecycle

Revision ID: 3cbc3564e708
Revises: 5aa5a32184fe
Create Date: 2026-08-12 11:42:23.015562

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3cbc3564e708'
down_revision: Union[str, None] = '5aa5a32184fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- status enum + column ---
    finding_status_enum = sa.Enum(
        "NEW", "CONFIRMED", "IN_REVIEW", "ACCEPTED_RISK", "FALSE_POSITIVE", "REMEDIATED", "REOPENED",
        name="finding_status",
    )
    finding_status_enum.create(op.get_bind())
    op.add_column("findings", sa.Column("status", finding_status_enum, nullable=False, server_default="NEW"))
    op.alter_column("findings", "status", server_default=None)

    # --- signature: dedup identity, partial unique index (NULL = excluded
    # from dedup, e.g. findings from a target_id-less job) ---
    op.add_column("findings", sa.Column("signature", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_findings_signature",
        "findings",
        ["signature"],
        unique=True,
        postgresql_where=sa.text("signature IS NOT NULL"),
    )

    # --- first_seen / last_seen: NOT NULL, backfilled from created_at for
    # existing rows (every Finding already represents at least one real
    # observation) ---
    op.add_column("findings", sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True))
    op.add_column("findings", sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE findings SET first_seen = created_at, last_seen = created_at WHERE first_seen IS NULL")
    op.alter_column("findings", "first_seen", nullable=False, server_default=sa.text("now()"))
    op.alter_column("findings", "last_seen", nullable=False, server_default=sa.text("now()"))

    # --- observation_count ---
    op.add_column("findings", sa.Column("observation_count", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("findings", "observation_count", server_default=None)

    # --- source_tools / observation_job_ids: backfilled from the finding's
    # own source_tool/job_id -- honest for existing data, never fabricating
    # a second tool or job that didn't actually contribute ---
    op.add_column("findings", sa.Column("source_tools", sa.JSON(), nullable=True))
    op.add_column("findings", sa.Column("observation_job_ids", sa.JSON(), nullable=True))
    op.execute(
        """
        UPDATE findings
        SET source_tools = json_build_array(source_tool),
            observation_job_ids = json_build_array(job_id::text)
        WHERE source_tools IS NULL
        """
    )
    op.alter_column("findings", "source_tools", nullable=False)
    op.alter_column("findings", "observation_job_ids", nullable=False)

    # --- finding_status_history: append-only audit trail ---
    op.create_table(
        "finding_status_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("finding_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # old_status/new_status reuse the finding_status type created above --
    # added via raw SQL rather than sa.Enum(...) in the column list, since
    # SQLAlchemy's DDL-event machinery would otherwise attempt to CREATE
    # TYPE a second time for a type shared across tables (same issue and
    # same fix as Phase 14's asset_change_events.severity).
    op.execute("ALTER TABLE finding_status_history ADD COLUMN old_status finding_status")
    op.execute("ALTER TABLE finding_status_history ADD COLUMN new_status finding_status NOT NULL")
    op.create_index("ix_finding_status_history_finding_id", "finding_status_history", ["finding_id"])

    # --- finding_relations: explicit, rule-generated correlation ---
    op.create_table(
        "finding_relations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("finding_id", sa.UUID(), nullable=False),
        sa.Column("related_finding_id", sa.UUID(), nullable=False),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("relation_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finding_id", "related_finding_id", "rule", name="uq_finding_relation"),
    )
    op.create_index("ix_finding_relations_finding_id", "finding_relations", ["finding_id"])
    op.create_index("ix_finding_relations_related_finding_id", "finding_relations", ["related_finding_id"])


def downgrade() -> None:
    op.drop_index("ix_finding_relations_related_finding_id", table_name="finding_relations")
    op.drop_index("ix_finding_relations_finding_id", table_name="finding_relations")
    op.drop_table("finding_relations")

    op.drop_index("ix_finding_status_history_finding_id", table_name="finding_status_history")
    op.drop_table("finding_status_history")

    op.drop_column("findings", "observation_job_ids")
    op.drop_column("findings", "source_tools")
    op.drop_column("findings", "observation_count")
    op.drop_column("findings", "last_seen")
    op.drop_column("findings", "first_seen")
    op.drop_index("uq_findings_signature", table_name="findings")
    op.drop_column("findings", "signature")
    op.drop_column("findings", "status")
    sa.Enum(name="finding_status").drop(op.get_bind())
