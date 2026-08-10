"""fix created_at server_default to use live now() function

Revision ID: 6ad0daaf9daa
Revises: c299a4211ca5
Create Date: 2026-08-10 00:58:05.677452

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6ad0daaf9daa'
down_revision: Union[str, None] = 'c299a4211ca5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bug: server_default="now()" (a bare Python string) was compiled by
    # SQLAlchemy as the SQL string literal 'now()', which Postgres casts to
    # a fixed timestamp AT TABLE-CREATION TIME rather than evaluating it
    # fresh per row -- every row got the same frozen created_at. The model
    # now uses sa.text("now()") (an unquoted function call); this migration
    # fixes the already-created columns in place.
    for table in ("jobs", "findings", "reports"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN created_at SET DEFAULT now()")


def downgrade() -> None:
    for table in ("jobs", "findings", "reports"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN created_at SET DEFAULT 'now()'")
