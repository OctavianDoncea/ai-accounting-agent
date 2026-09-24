"""vendor account memory

Revision ID: 0009_vendor_memory
Revises: 0008_user_scoped_data
Create Date: 2026-09-24 15:29:00
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0009_vendor_memory'
down_revision: Union[str, None] = '0008_user_scoped_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'vendor_account_memory',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('vendor_key', sa.String(length=320), nullable=False),
        sa.Column('vendor_display', sa.String(length=320), nullable=False),
        sa.Column('account_code', sa.String(length=20), nullable=False),
        sa.Column('times_seen', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    )
    op.create_foreign_key('fk_vendor_memory_user_id', 'vendor_account_memory', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_vendor_account_memory_user_id', 'vendor_account_memory', ['user_id'])
    op.create_index('ix_vendor_account_memory_vendor_key', 'vendor_account_memory', ['vendor_key'])
    op.create_unique_constraint('uq_vendor_memory_user_vendor_account', 'vendor_account_memory', ['user_id', 'vendor_key', 'account_code'])

def downgrade() -> None:
    op.drop_constraint('uq_vendor_memory_user_vendor_account', 'vendor_account_memory', type_='unique')
    op.drop_index('ix_vendor_account_memory_vendor_key', table_name='vendor_account_memory')
    op.drop_index('ix_vendor_account_memory_user_id', table_name='vendor_account_memory')
    op.drop_constraint('fk_vendor_memory_user_id', 'vendor_account_memory', type_='foreignkey')
    op.drop_table('vendor_account_memory')