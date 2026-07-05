"""journal entry type (bill vs payment)

Revision ID: 0006_journal_entry_type
Revises: d4e5f6a7b8c9
Create Date: 2026-07-03 11:05:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0006_journal_entry_type'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

journal_entry_type_enum = postgresql.ENUM('BILL', 'PAYMENT', name='journal_entry_type')

def upgrade() -> None:
    bind = op.get_bind()
    journal_entry_type_enum.create(bind, checkfirst=True)

    op.add_column(
        'journal_entries',
        sa.Column(
            'entry_type',
            postgresql.ENUM(name='journal_entry_type', create_type=False),
            nullable=False,
            server_default='BILL'
        )
    )
    op.create_index('ix_journal_entries_entry_type', 'journal_entries', ['entry_type'])

def downgrade() -> None:
    op.drop_index('ix_journal_entries_entry_type', table_name='journal_entries')
    op.drop_column('journal_entries', 'entry_type')
    bind = op.get_bind()
    journal_entry_type_enum.drop(bind, checkfirst=True)