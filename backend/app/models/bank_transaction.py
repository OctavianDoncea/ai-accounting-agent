import enum
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, DateTime, Date, Enum, Text, Numeric, ForeignKey, Integer, Float, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class TransactionDirection(str, enum.Enum):
    OUTFLOW = 'OUTFLOW'
    INFLOW = 'INFLOW'


class BankTransactionStatus(str, enum.Enum):
    UNMATCHED = 'UNMATCHED'
    MATCHED = 'MATCHED'
    IGNORED = 'IGNORED'


class ReconciliationRun(Base):
    """One bank-statement upload and the reconciliation report generated from it"""

    __tablename__ = 'reconciliation_runs'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    bank_transaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmatched_bank_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmatched_journal_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_matched_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal('0'), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    transactions: Mapped[list['BankTransaction']] = relationship(back_populates='run', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<ReconciliationRun {self.id} matched={self.matched_count}/{self.bank_transaction_count}>'


class BankTransaction(Base):
    __tablename__ = 'bank_transactions'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('reconciliation_runs.id', ondelete='CASCADE'), nullable=False, index=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    direction: Mapped[TransactionDirection] = mapped_column(Enum(TransactionDirection, name='transaction_direction'), nullable=False)
    status: Mapped[BankTransactionStatus] = mapped_column(Enum(BankTransactionStatus, name='bank_transaction_status'), default=BankTransactionStatus.UNMATCHED, nullable=False, index=True)
    matched_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('journal_entries.id', ondelete='SET NULL'), nullable=True, index=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_row: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run: Mapped['ReconciliationRun'] = relationship(back_populates='transactions')

    def __repr__(self) -> str:
        return f'<BankTransaction {self.transaction_date} {self.description[:25]} {self.amount} {self.status}>'