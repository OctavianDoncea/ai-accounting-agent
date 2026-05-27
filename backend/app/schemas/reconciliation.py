import uuid
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from app.models.bank_transaction import BankTransactionStatus, TransactionDirection

class BankTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_date: date | None
    description: str
    amount: Decimal
    direction: TransactionDirection
    status: BankTransactionStatus
    matched_journal_entry_id: uuid.UUID | None
    match_confidence: float | None
    match_reasoning: str | None


class UnmatchedJournalEntryOut(BaseModel):
    journal_entry_id: uuid.UUID
    entry_date: date | None
    vendor_name: str
    amount: Decimal


class ReconciliationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    created_at: datetime
    bank_transaction_count: int
    matched_count: int
    unmatched_bank_count: int
    unmatched_journal_count: int
    total_matched_amount: Decimal
    summary: str | None


class ReconciliationSummaryOut(ReconciliationRunOut):
    matched: list[BankTransactionOut] = Field(default_factory=list)
    unmatched_bank: list[BankTransactionOut] = Field(default_factory=list)
    ignored: list[BankTransactionOut] = Field(default_factory=list)
    unmatched_journal: list[UnmatchedJournalEntryOut] = Field(default_factory=list)