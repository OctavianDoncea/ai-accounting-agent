"""make invoice raw_text nullable
Revision ID: a1b2c3d4e5f6
Revises: f20e47f5f841
Create Date: 2026-05-22 22:20:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f20e47f5f841'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.alter_column('invoices', 'raw_text', existing_type=sa.Text(), nullable=True)

def downgrade() -> None:
    op.alter_column('invoices', 'raw_text', existing_type=sa.Text(), nullable=False)