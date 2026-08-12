"""generalize target into asset model

Phase 13 -- Target becomes a special case of Asset: same table (renamed),
same primary keys, same FK from jobs.target_id (Postgres updates the FK
target automatically on table rename). Purely additive from a data
perspective -- no row is dropped, no existing column value changes meaning.
`Target`/`TargetType`/`target_metadata` keep working unchanged as Python
aliases (see app/models/target.py); this migration only touches the DB side.

Revision ID: 392e4638a4d8
Revises: 3a248ef9f137
Create Date: 2026-08-12 09:10:09.830995

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '392e4638a4d8'
down_revision: Union[str, None] = '3a248ef9f137'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Table + column renames. Postgres updates the jobs.target_id FK and
    #    all indexes/constraints to point at the new names automatically.
    op.rename_table("targets", "assets")
    op.alter_column("assets", "target_type", new_column_name="type")
    op.alter_column("assets", "target_metadata", new_column_name="asset_metadata")

    # 2. Rename the enum type and add the new values the Asset model
    #    introduces (HOST/IP/DOMAIN/URL/CONTAINER/LAB/OTHER already exist).
    #    ADD VALUE cannot run inside the same transaction that uses the new
    #    value, and on older Postgres cannot run in a transaction block at
    #    all -- isolate it in an autocommit block.
    op.execute("ALTER TYPE target_type RENAME TO asset_type")
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE asset_type ADD VALUE IF NOT EXISTS 'SUBDOMAIN'")
        op.execute("ALTER TYPE asset_type ADD VALUE IF NOT EXISTS 'SERVICE'")
        op.execute("ALTER TYPE asset_type ADD VALUE IF NOT EXISTS 'LAB_RESOURCE'")

    # 3. New criticality field -- manually assigned (Phase 13 scope), never
    #    auto-computed until the Risk Score work (Phase 15) exists.
    criticality_enum = sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="asset_criticality")
    criticality_enum.create(op.get_bind())
    op.add_column(
        "assets",
        sa.Column("criticality", criticality_enum, nullable=False, server_default="MEDIUM"),
    )
    op.alter_column("assets", "criticality", server_default=None)

    # 4. tags / technologies -- plain JSON arrays, additive.
    op.add_column("assets", sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"))
    op.alter_column("assets", "tags", server_default=None)
    op.add_column("assets", sa.Column("technologies", sa.JSON(), nullable=False, server_default="[]"))
    op.alter_column("assets", "technologies", server_default=None)

    # 5. first_seen / last_seen -- deliberately nullable and NOT backfilled
    #    from created_at: per spec these reflect real observed activity
    #    (Job history), not administrative record creation. Backfilled from
    #    existing jobs below; an asset that was created but never scanned
    #    stays NULL/NULL, which is the correct, honest state.
    op.add_column("assets", sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assets", sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE assets
        SET first_seen = activity.first_seen,
            last_seen = activity.last_seen
        FROM (
            SELECT target_id,
                   MIN(created_at) AS first_seen,
                   MAX(COALESCE(finished_at, created_at)) AS last_seen
            FROM jobs
            WHERE target_id IS NOT NULL
            GROUP BY target_id
        ) AS activity
        WHERE assets.id = activity.target_id
        """
    )


def downgrade() -> None:
    op.drop_column("assets", "last_seen")
    op.drop_column("assets", "first_seen")
    op.drop_column("assets", "technologies")
    op.drop_column("assets", "tags")
    op.drop_column("assets", "criticality")
    sa.Enum(name="asset_criticality").drop(op.get_bind())

    # Enum values added by ADD VALUE cannot be dropped in Postgres without
    # rebuilding the type; the rename back is safe, the added values
    # (SUBDOMAIN/SERVICE/LAB_RESOURCE) are simply left unused on downgrade.
    op.execute("ALTER TYPE asset_type RENAME TO target_type")

    op.alter_column("assets", "asset_metadata", new_column_name="target_metadata")
    op.alter_column("assets", "type", new_column_name="target_type")
    op.rename_table("assets", "targets")
