import logging
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.journal_entry import JournalEntry, JournalEntryStatus, JournalEntryLines
from app.models.chart_of_accounts import ChartOfAccount
from app.models.invoice import Invoice
from app.schemas.journal_entry import ClassificationResult

log = logging.getLogger(__name__)

ACCOUNTS_PAYABLE_CODE = '2000'
FALLBACK_EXPENSE_CODE = '7900'
FALLBACK_TAX_CODE = '6920'

def _account_map(db: Session) -> dict[str, ChartOfAccount]:
    return {a.account_code: a for a in db.query(ChartOfAccount).all()}

def build_journal_entry(db: Session, invoice: Invoice, classification: ClassificationResult) -> tuple[JournalEntry, list[str]]:
    accounts = _account_map(db)
    notes: list[str] = []

    ap_account = accounts.get(ACCOUNTS_PAYABLE_CODE)
    if ap_account is None:
        raise ValueError(f'Accounts Payable account ({ACCOUNTS_PAYABLE_CODE}) missing from chart of accounts')

    by_index = {c.line_index: c for c in classification.classifications}

    entry = JournalEntry(
        invoice_id=invoice.id,
        entry_date=invoice.invoice_date or date.today(),
        description = _description(invoice),
        status = JournalEntryStatus.DRAFT
    )

    total_debit = Decimal('0')

    # 1. One debit line per invoice line item
    for i, li in enumerate(invoice.line_items):
        cls = by_index.get(i)
        account = accounts.get(cls.account_code) if cls else None
        confidence = cls.confidence if cls else None

        if accounts is None:
            account = accounts.get(FALLBACK_EXPENSE_CODE)
            confidence = 0.2
            notes.append(
                f"Line {i} ('{li.description[:40]}') could not be classified to a valid account; fell back to {FALLBACK_EXPENSE_CODE}."
            )

        entry.lines.append(JournalEntryLines(
            account_id=account.id,
            debit_amount=li.amount,
            credit_amount=Decimal('0'),
            description=li.description,
            confidence_score=confidence,
        ))
        total_debit += li.amount

    # 2. Tax debit line (if any tax on the invoice)
    if invoice.tax is not None and invoice.tax > 0:
        tax_code = classification.tax_account_code or FALLBACK_TAX_CODE
        tax_account = accounts.get(tax_code) or accounts.get(FALLBACK_TAX_CODE)

        if tax_account is None:
            tax_account = accounts.get(FALLBACK_EXPENSE_CODE)
            notes.append('Tax account unavailable; fell back to misc expense.')
        
        entry.lines.append(
            JournalEntryLines(
                account_id=tax_account.id,
                debit_amount=invoice.tax,
                credit_amount=Decimal('0'),
                description='Sales tax',
                confidence_score=None,
            )
        )
        total_debit += invoice.tax

    # 3. Single credit line: Accounts Payable for the grand total
    credit_total = invoice.total if invoice.total is not None else total_debit
    if invoice.total is None:
        notes.append("Invoice total missing; credited Accounts Payable with the sum of debits.")
 
    entry.lines.append(
        JournalEntryLines(
            account_id=ap_account.id,
            debit_amount=Decimal('0'),
            credit_amount=credit_total,
            description=f"Payable to {invoice.vendor_name or 'vendor'}",
            confidence_score=None,
        )
    )
 
    entry.total_debit = total_debit
    entry.total_credit = credit_total
    return entry, notes

def _description(invoice: Invoice) -> str:
    parts = []
    if invoice.vendor_name:
        parts.append(invoice.vendor_name)

    if invoice.invoice_number:
        parts.append(f'Invoice #{invoice.invoice_number}')

    return ' '.join(parts) if parts else f'Invoice {invoice.id}'