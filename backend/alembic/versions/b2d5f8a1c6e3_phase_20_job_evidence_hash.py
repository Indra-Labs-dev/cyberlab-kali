"""phase 20 job evidence hash

Revision ID: b2d5f8a1c6e3
Revises: a1c4e6f9b3d2
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d5f8a1c6e3'
down_revision: Union[str, None] = 'a1c4e6f9b3d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("evidence_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "evidence_sha256")
