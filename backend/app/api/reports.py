import uuid
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.chart_of_accounts import ChartOfAccount, AccountType, NormalBalance
from app.models.journal_entry import JournalEntry, JournalEntryStatus, JournalEntryLines, JournalEntryType
from app.models.invoice import Invoice
from app.security import get_current_user_id

router = APIRouter(prefix='/reports', tags=['reports'])

class TrialBalanceRow(BaseModel):
    account_code: str
    account_name: str
    account_type: AccountType
    normal_balance: NormalBalance
    total_debits: Decimal
    total_credits: Decimal
    balance: Decimal


class TrialBalance(BaseModel):
    rows: list[TrialBalanceRow] = Field(default_factory=list)
    total_debits: Decimal = Decimal('0')
    total_credits: Decimal = Decimal('0')
    is_balanced: bool = False


@router.get('/trial-balance', response_model=TrialBalance)
def trial_balance(db: Session = Depends(get_db), user_id: uuid.UUID | None = Depends(get_current_user_id)) -> TrialBalance:
    rows_q = (
        db.query(
            ChartOfAccount.account_code,
            ChartOfAccount.account_name,
            ChartOfAccount.account_type,
            ChartOfAccount.normal_balance,
            func.coalesce(func.sum(JournalEntryLines.debit_amount), 0).label('debits'),
            func.coalesce(func.sum(JournalEntryLines.credit_amount), 0).label('credits'),
        )
        .join(JournalEntryLines, JournalEntryLines.account_id == ChartOfAccount.id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLines.journal_entry_id)
        .filter(JournalEntry.status == JournalEntryStatus.POSTED)
    )
    if user_id is not None:
        rows_q = rows_q.filter(JournalEntry.user_id == user_id)
    rows_q = rows_q.group_by(
        ChartOfAccount.account_code,
        ChartOfAccount.account_name,
        ChartOfAccount.account_type,
        ChartOfAccount.normal_balance
    ).order_by(ChartOfAccount.account_code).all()

    rows: list[TrialBalanceRow] = []
    total_debits = Decimal('0')
    total_credits = Decimal('0')
    
    for r in rows_q:
        debits = Decimal(r.debits)
        credits = Decimal(r.credits)
        if r.normal_balance == NormalBalance.DEBIT:
            balance = debits - credits
        else:
            balance = credits - debits
        rows.append(
            TrialBalanceRow(
                account_code=r.account_code,
                account_name=r.account_name,
                account_type=r.account_type,
                normal_balance=r.normal_balance,
                total_debits=debits,
                total_credits=credits,
                balance=balance,
            )
        )
        total_debits += debits
        total_credits += credits

    return (TrialBalance(rows=rows, total_debits=total_debits, total_credits=total_credits, is_balanced=abs(total_debits - total_credits) <= Decimal('0.01')))

class ExpenseBreakdownRow(BaseModel):
    account_code: str
    account_name: str
    total: Decimal


@router.get('/expense-breakdown', response_model=list[ExpenseBreakdownRow])
def expense_breakdown(db: Session = Depends(get_db), user_id: uuid.UUID | None = Depends(get_current_user_id)) -> list[ExpenseBreakdownRow]:
    query = (
        db.query(
            ChartOfAccount.account_code,
            ChartOfAccount.account_name,
            func.coalesce(func.sum(JournalEntryLines.debit_amount), 0).label("total"),
        )
        .join(JournalEntryLines, JournalEntryLines.account_id == ChartOfAccount.id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLines.journal_entry_id)
        .filter(
            JournalEntry.status == JournalEntryStatus.POSTED,
            ChartOfAccount.account_type == AccountType.EXPENSE,
        )
    )
    if user_id is not None:
        query = query.filter(JournalEntry.user_id == user_id)
    rows = (
        query
        .group_by(ChartOfAccount.account_code, ChartOfAccount.account_name)
        .having(func.sum(JournalEntryLines.debit_amount) > 0)
        .order_by(func.sum(JournalEntryLines.debit_amount).desc())
        .all()
    )
    return [
        ExpenseBreakdownRow(account_code=r.account_code, account_name=r.account_name, total=Decimal(r.total))
        for r in rows
    ]

# AP aging report
class APAgingRow(BaseModel):
    invoice_id: str | None
    journal_entry_id: str
    vendor_name: str
    invoice_number: str | None
    entry_date: date
    days_outstanding: int
    bucket: str
    amount: Decimal


class APAgingBucket(BaseModel):
    bucket: str
    count: int
    total: Decimal


class APAgingReport(BaseModel):
    as_of: date
    rows: list[APAgingRow] = Field(default_factory=list)
    buckets: list[APAgingBucket] = Field(default_factory=list)
    total_outstanding: Decimal = Decimal('0')


_BUCKETS = ['0-30', '31-60', '61-90', '90+']

def _bucket_for(days: int) -> str:
    if days <= 30:
        return '0-30'
    if days <= 60:
        return '31-60'
    if days <= 90:
        return '61-90'
    return '90+'

@router.get('/ap-aging', response_model=APAgingReport)
def ap_aging(db: Session = Depends(get_db), user_id: uuid.UUID | None = Depends(get_current_user_id)) -> APAgingReport:
    """Accounts Payable aging, every posted bill that hasn't been paid yet, bucketed by how long it's been outstanding (0-30, 31-60, 61-90, 90+ days)"""

    today = date.today()
    paid_q = db.query(JournalEntry.invoice_id).filter(JournalEntry.entry_type == JournalEntryType.PAYMENT, JournalEntry.status == JournalEntryStatus.POSTED)

    if user_id is not None:
        paid_q = paid_q.filter(JournalEntry.user_id == user_id)

    paid_invoice_ids = {row[0] for row in paid_q.all() if row[0] is not None}
    bill_q = (db.query(JournalEntry, Invoice).outerjoin(Invoice, JournalEntry.invoice_id == Invoice.id)
               .filter(JournalEntry.entry_type == JournalEntryType.BILL, JournalEntry.status == JournalEntryStatus.POSTED))

    if user_id is not None:
        bill_q = bill_q.filter(JournalEntry.user_id == user_id)

    rows: list[APAgingRow] = []
    buckets_totals: dict[str, dict] = {b: {'count': 0, 'total': Decimal('0')} for b in _BUCKETS}
    total_outstanding = Decimal('0')

    for je, inv in bill_q.all():
        if je.invoice_id is not None and je.invoice_id in paid_invoice_ids:
            continue

        days = (today - je.entry_date).days
        days = max(0, days)
        bucket = _bucket_for(days)
        amount = je.total_credit
        rows.append(APAgingRow(
            invoice_id = str(je.invoice_id) if je.invoice_id is not None else None,
            journal_entry_id = str(je.id),
            vendor_name = (inv.vendor_name if inv and inv.vendor_name else je.description) or '-',
            invoice_number = inv.invoice_number if inv else None,
            entry_date = je.entry_date,
            days_outstanding = days,
            bucket = bucket,
            amount = amount,
        ))
        buckets_totals[bucket]['count'] += 1
        buckets_totals[bucket]['total'] += amount
        total_outstanding += amount

    rows.sort(key=lambda r: r.days_outstanding, reverse=True)

    return APAgingReport(
        as_of = today,
        rows = rows,
        buckets = [APAgingBucket(bucket=b, count=buckets_totals[b]['count'], total=buckets_totals[b]['total']) for b in _BUCKETS],
        total_outstanding = total_outstanding,
    )

# Vendor memory / classification accuracy
class VendorAccountStat(BaseModel):
    account_code: int
    times_seen: int


class VendorStatsRow(BaseModel):
    vendor: str
    total_posts: int
    accounts: list[VendorAccountStat] = Field(default_factory=list)


@router.get('/vendor-memory', response_model=list[VendorStatsRow])
def vendor_memory(db: Session = Depends(get_db), user_id: uuid.UUID | None = Depends(get_current_user_id)) -> list[VendorStatsRow]:
    from app.services.vendor_memory_service import vendor_stats

    stats = vendor_stats(db, user_id)
    return [VendorStatsRow(
        vendor = s['vendor'],
        total_posts = s['total_posts'],
        accounts = [VendorAccountStat(**a) for a in s['accounts']]
    ) for s in stats]