"""per-user data isolation.

Revision ID: 0008_user_scoped_data
Revises: 0007_users
"""
import sqlalchemy as sa
from typing import Sequence, Union
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0008_user_scoped_data'
down_revision: Union[str, None] = '0007_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ['invoices', 'journal_entries', 'reconciliation_runs', 'agent_logs']

def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f'fk_{table}_user_id', table, 'users', ['user_id'], ['id'], ondelete='CASCADE')
        op.create_index(f'ix_{table}_user_id', table, ['user_id'])

def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f'ix_{table}_user_id', table_name=table)
        op.drop_constraint(f'fk_{table}_user_id', table, type_='foreignkey')
        op.drop_column(table, 'user_id')