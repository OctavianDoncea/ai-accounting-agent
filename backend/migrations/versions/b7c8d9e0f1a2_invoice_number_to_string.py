"""invoice_number column to string

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-22 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'invoices',
        'invoice_number',
        existing_type=sa.Date(),
        type_=sa.String(length=100),
        existing_nullable=True,
        postgresql_using='invoice_number::text',
    )


def downgrade() -> None:
    op.alter_column(
        'invoices',
        'invoice_number',
        existing_type=sa.String(length=100),
        type_=sa.Date(),
        existing_nullable=True,
        postgresql_using='invoice_number::date',
    )
