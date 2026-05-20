import enum
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, DateTime, Date, Enum, Text, Numeric, ForeignKey, Float, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class JournalEntryStatus(str, enum.Enum):
    DRAFT = 'DRAFT'
    POSTED = 'POSTED'
    REVERSED = 'REVERSED'


class JournalEntry(Base):
    __tablename__ = 'journal_entries'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('invoices.id', ondelete='SET NULL'), nullable=True, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[JournalEntryStatus] = mapped_column(Enum(JournalEntryStatus, name='journal_entry_status'), default=JournalEntryStatus.DRAFT, nullable=False, index=True)
    total_debit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=Decimal('0'))
    total_credit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=Decimal('0'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    lines: Mapped[list['JournalEntryLines']] = relationship(back_populates='journal_entry', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<JournalEntry {self.id} - {self.description[:30]} - {self.status}>'


class JournalEntryLines(Base):
    __tablename__ = 'journal_entry_lines'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('journal_entries.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('chart_of_accounts.id'), nullable=False, index=True)
    debit_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=Decimal('0'))
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=Decimal('0'))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    journal_entry: Mapped['JournalEntry'] = relationship(back_populates='lines')

    def __repr__(self) -> str:
        side = 'DR' if self.debit_amount > 0 else 'CR'
        amount = self.debit_amount if self.debit_amount > 0 else self.credit_amount
        return f'<JournalEntryLine {side} {amount} acct={self.account_id}>'