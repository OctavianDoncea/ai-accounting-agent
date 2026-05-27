from decimal import Decimal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.chart_of_accounts import ChartOfAccount, AccountType, NormalBalance
from app.models.journal_entry import JournalEntry, JournalEntryStatus, JournalEntryLines

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
def trial_balance(db: Session = Depends(get_db)) -> TrialBalance:
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
        .group_by(
            ChartOfAccount.account_code,
            ChartOfAccount.account_name,
            ChartOfAccount.account_type,
            ChartOfAccount.normal_balance,
        )
        .order_by(ChartOfAccount.account_code)
        .all()
    )

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
def expense_breakdown(db: Session = Depends(get_db)) -> list[ExpenseBreakdownRow]:
    rows = (
        db.query(
            ChartOfAccount.account_code,
            ChartOfAccount.account_name,
            func.coalesce(func.sum(JournalEntryLines.debit_amount), 0).label('total'),
        )
        .join(JournalEntryLines, JournalEntryLines.account_id == ChartOfAccount.id)
        .join(JournalEntry, JournalEntry.id == JournalEntryLines.journal_entry_id)
        .filter(JournalEntry.status == JournalEntryStatus.POSTED, ChartOfAccount.account_type == AccountType.EXPENSE)
        .group_by(ChartOfAccount.account_code, ChartOfAccount.account_name)
        .having(func.sum(JournalEntryLines.debit_amount) > 0)
        .order_by(func.sum(JournalEntryLines.debit_amount).desc())
        .all()
    )   

    return [
        ExpenseBreakdownRow(account_code=r.account_code, account_name=r.account_name, total=Decimal(r.total))
        for r in rows
    ]