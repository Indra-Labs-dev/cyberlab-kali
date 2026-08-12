"""security graph edges

Revision ID: 496b351d1744
Revises: 3cbc3564e708
Create Date: 2026-08-12 15:40:41.395521

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '496b351d1744'
down_revision: Union[str, None] = '3cbc3564e708'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "graph_edges",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_type", sa.String(length=32), nullable=False),
        sa.Column("from_id", sa.String(length=512), nullable=False),
        sa.Column("to_type", sa.String(length=32), nullable=False),
        sa.Column("to_id", sa.String(length=512), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("edge_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("from_type", "from_id", "to_type", "to_id", "relation", name="uq_graph_edge"),
    )
    op.create_index("ix_graph_edges_from", "graph_edges", ["from_type", "from_id"])
    op.create_index("ix_graph_edges_to", "graph_edges", ["to_type", "to_id"])


def downgrade() -> None:
    op.drop_index("ix_graph_edges_to", table_name="graph_edges")
    op.drop_index("ix_graph_edges_from", table_name="graph_edges")
    op.drop_table("graph_edges")
