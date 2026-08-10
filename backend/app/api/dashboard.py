import uuid
from datetime import datetime, date
from decimal import Decimal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.bank_transaction import ReconciliationRun
from app.models.invoice import Invoice, InvoiceStatus
from app.models.journal_entry import JournalEntry, JournalEntryStatus
from app.security import get_current_user_id

router = APIRouter(prefix='/dashboard', tags=['dashboard'])

class RecentInvoiceItem(BaseModel):
    id: uuid.UUID
    filename: str
    vendor_name: str | None
    status: InvoiceStatus
    total: Decimal | None
    currency: str
    upload_date: datetime


class RecentRunItem(BaseModel):
    id: uuid.UUID
    filename: str
    created_at: datetime
    matched_count: int
    unmatched_bank_count: int
    unmatched_journal_count: int
    total_matched_amount: Decimal


class DashboardSummary(BaseModel):
    invoice_counts: dict[str, int] = Field(default_factory=dict)
    total_invoices: int = 0
    journal_entries_posted: int = 0
    journal_entries_draft: int = 0
    total_posted_value: Decimal = Decimal('0')
    reconciliation_runs: int = 0
    recent_invoices: list[RecentInvoiceItem] = Field(default_factory=list)
    recent_runs: list[RecentRunItem] = Field(default_factory=list)


@router.get('/summary', response_model=DashboardSummary)
def get_summary(db: Session = Depends(get_db), user_id: uuid.UUID | None = Depends(get_current_user_id)) -> DashboardSummary:
    invoice_counts_query = db.query(Invoice.status, func.count())
    if user_id is not None:
        invoice_counts_query = invoice_counts_query.filter(Invoice.user_id == user_id)
    invoice_counts = {s.value: 0 for s in InvoiceStatus}
    for status, n in invoice_counts_query.group_by(Invoice.status).all():
        invoice_counts[status.value] = n

    je_posted_query = db.query(
        func.count(), func.coalesce(func.sum(JournalEntry.total_credit), 0)
    ).filter(JournalEntry.status == JournalEntryStatus.POSTED)
    je_draft_query = db.query(func.count()).filter(JournalEntry.status == JournalEntryStatus.DRAFT)
    runs_count_query = db.query(func.count(ReconciliationRun.id))
    if user_id is not None:
        je_posted_query = je_posted_query.filter(JournalEntry.user_id == user_id)
        je_draft_query = je_draft_query.filter(JournalEntry.user_id == user_id)
        runs_count_query = runs_count_query.filter(ReconciliationRun.user_id == user_id)

    je_posted = je_posted_query.first()
    je_draft = je_draft_query.scalar()
    runs_count = runs_count_query.scalar() or 0

    recent_invoices_query = db.query(Invoice)
    recent_runs_query = db.query(ReconciliationRun)
    if user_id is not None:
        recent_invoices_query = recent_invoices_query.filter(Invoice.user_id == user_id)
        recent_runs_query = recent_runs_query.filter(ReconciliationRun.user_id == user_id)

    recent_invoices = recent_invoices_query.order_by(Invoice.upload_date.desc()).limit(5).all()
    recent_runs = recent_runs_query.order_by(ReconciliationRun.created_at.desc()).limit(5).all()

    return DashboardSummary(
        invoice_counts=invoice_counts,
        total_invoices=sum(invoice_counts.values()),
        journal_entries_posted=je_posted[0] or 0,
        journal_entries_draft=je_draft or 0,
        total_posted_value=je_posted[1] or Decimal('0'),
        reconciliation_runs=runs_count,
        recent_invoices=[
            RecentInvoiceItem(
                id=inv.id, filename=inv.filename, vendor_name=inv.vendor_name,
                status=inv.status, total=inv.total, currency=inv.currency,
                upload_date=inv.upload_date
            )
            for inv in recent_invoices
        ],
        recent_runs=[
            RecentRunItem(
                id=r.id, filename=r.filename, created_at=r.created_at,
                matched_count=r.matched_count,
                unmatched_bank_count=r.unmatched_bank_count,
                unmatched_journal_count=r.unmatched_journal_count,
                total_matched_amount=r.total_matched_amount
            )
            for r in recent_runs
        ]
    )