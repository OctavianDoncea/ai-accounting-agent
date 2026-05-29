import uuid
from datetime import date
from decimal import Decimal
from app.models.bank_transaction import BankTransactionStatus, TransactionDirection
from app.models.invoice import Invoice
from app.models.journal_entry import JournalEntry, JournalEntryLines, JournalEntryStatus
from app.services.reconciliation_processor import run_reconciliation

def _post_journal_entry(db, *, vendor: str, total: Decimal, entry_date: date) -> None:
    inv = Invoice(
        id=uuid.uuid4(),
        filename=f'{vendor}.pdf',
        file_path=f'/tmp/{vendor}.pdf',
        status='POSTED',
        vendor_name=vendor,
        invoice_date=entry_date,
        total=total,
        currency='USD'
    )
    db.add(inv)
    db.flush()

    from app.models.chart_of_accounts import ChartOfAccount
    ap = db.query(ChartOfAccount).filter_by(account_code='2000').first()
    misc = db.query(ChartOfAccount).filter_by(account_code='7900').first()

    je = JournalEntry(
        id=uuid.uuid4(),
        invoice_id=inv.id,
        entry_date=entry_date,
        description=f'{vendor} test',
        status=JournalEntryStatus.POSTED,
        total_debit=total,
        total_credit=total,
    )
    je.lines.append(JournalEntryLines(account_id=misc.id, debit_amount=total, credit_amount=Decimal('0')))
    je.lines.append(JournalEntryLines(account_id=ap.id, debit_amount=Decimal('0'), credit_amount=total))
    db.add(je)
    db.commit()

class TestReconciliation:
    def test_three_matches_one_unmatched_payment(self, db):
        _post_journal_entry(db, vendor='CloudHost Solutions Inc.', total=Decimal('414.60'), entry_date=date(2026, 4, 15))
        _post_journal_entry(db, vendor='Office Depot', total=Decimal('508.77'), entry_date=date(2026, 4, 22))
        _post_journal_entry(db, vendor='Brightman & Associates LLP', total=Decimal('2100.00'), entry_date=date(2026, 5, 1))

        csv = (
            b"Date,Description,Amount\n"
            b"2026-05-05,CLOUDHOST SOLUTIONS PYMT ACH,-414.60\n"
            b"2026-05-08,OFFICE DEPOT #558 PURCHASE,-508.77\n"
            b"2026-05-10,STARBUCKS STORE 4471,-18.45\n"
            b"2026-05-12,BRIGHTMAN ASSOCIATES LLP ACH PMT,-2100.00\n"
        )
        run = run_reconciliation(db, 'stmt.csv', csv)

        assert run.matched_count == 3
        assert run.unmatched_bank_count == 1
        assert run.unmatched_journal_count == 0
        assert run.total_matched_amount == Decimal('3023.37')

    def test_unpaid_bill_detection(self, db):
        _post_journal_entry(db, vendor='CloudHost Solutions Inc.', total=Decimal('414.60'), entry_date=date(2026, 4, 15))
        _post_journal_entry(db, vendor='Office Depot', total=Decimal('508.77'), entry_date=date(2026, 4, 22))

        csv = b"Date,Description,Amount\n2026-05-05,CLOUDHOST SOLUTIONS PYMT,-414.60\n"
        run = run_reconciliation(db, 'stmt.csv', csv)

        assert run.matched_count == 1
        assert run.unmatched_bank_count == 0
        assert run.unmatched_journal_count == 1

    def test_inflows_ignored(self, db):
        csv = (
            b"Date,Description,Amount\n"
            b"2026-05-02,PAYROLL DEPOSIT,5000.00\n"
        )
        run = run_reconciliation(db, 'stmt.csv', csv)
        assert run.bank_transaction_count == 1

        from app.models.bank_transaction import BankTransaction
        txns = db.query(BankTransaction).filter(BankTransaction.run_id == run.id).all()
        deposit = next(t for t in txns if t.description == 'PAYROLL DEPOSIT')
        assert deposit.status == BankTransactionStatus.IGNORED
        assert deposit.direction == TransactionDirection.INFLOW

    def test_amount_match_but_unrelated_name_stays_unmatched(self, db):
        _post_journal_entry(db, vendor='CloudHost Solutions Inc.', total=Decimal('100.00'), entry_date=date(2026, 4, 15))
        csv = b"Date,Description,Amount\n2026-05-05,XYZ TOTALLY DIFFERENT,-100.00\n"
        run = run_reconciliation(db, 'stmt.csv', csv)
        assert run.matched_count == 0
        assert run.unmatched_bank_count == 1