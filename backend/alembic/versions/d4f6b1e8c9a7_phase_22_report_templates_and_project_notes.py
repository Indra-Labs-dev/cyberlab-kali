"""phase 22 report templates and project notes

Revision ID: d4f6b1e8c9a7
Revises: c3e7a9f2d5b8
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f6b1e8c9a7'
down_revision: Union[str, None] = 'c3e7a9f2d5b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    report_template = sa.Enum("EXECUTIVE", "TECHNICAL", "EVIDENCE_PACKAGE", name="report_template")
    report_template.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "reports",
        sa.Column("template", report_template, nullable=False, server_default="TECHNICAL"),
    )
    op.alter_column("reports", "template", server_default=None)

    op.add_column("projects", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "notes")

    op.drop_column("reports", "template")
    sa.Enum(name="report_template").drop(op.get_bind(), checkfirst=True)
