"""add reconciliation tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-27 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reconciliation_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('bank_transaction_count', sa.Integer(), nullable=False),
        sa.Column('matched_count', sa.Integer(), nullable=False),
        sa.Column('unmatched_bank_count', sa.Integer(), nullable=False),
        sa.Column('unmatched_journal_count', sa.Integer(), nullable=False),
        sa.Column('total_matched_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'bank_transactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('direction', sa.Enum('OUTFLOW', 'INFLOW', name='transaction_direction'), nullable=False),
        sa.Column('status', sa.Enum('UNMATCHED', 'MATCHED', 'IGNORED', name='bank_transaction_status'), nullable=False),
        sa.Column('matched_journal_entry_id', sa.UUID(), nullable=True),
        sa.Column('match_confidence', sa.Float(), nullable=True),
        sa.Column('match_reasoning', sa.Text(), nullable=True),
        sa.Column('raw_row', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['reconciliation_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['matched_journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bank_transactions_run_id'), 'bank_transactions', ['run_id'], unique=False)
    op.create_index(op.f('ix_bank_transactions_status'), 'bank_transactions', ['status'], unique=False)
    op.create_index(op.f('ix_bank_transactions_matched_journal_entry_id'), 'bank_transactions', ['matched_journal_entry_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bank_transactions_matched_journal_entry_id'), table_name='bank_transactions')
    op.drop_index(op.f('ix_bank_transactions_status'), table_name='bank_transactions')
    op.drop_index(op.f('ix_bank_transactions_run_id'), table_name='bank_transactions')
    op.drop_table('bank_transactions')
    op.drop_table('reconciliation_runs')
    op.execute('DROP TYPE IF EXISTS bank_transaction_status')
    op.execute('DROP TYPE IF EXISTS transaction_direction')
