"""Tests for payment recording triggered by bank reconciliation"""

import uuid
from datetime import date
from decimal import Decimal
from app.models.invoice import Invoice
from app.models.journal_entry import JournalEntry, JournalEntryLines, JournalEntryStatus, JournalEntryType
from app.services.reconciliation_processor import run_reconciliation

def _post_bill(db, *, vendor: str, total: Decimal, entry_date: date) -> uuid.UUID:
    inv = Invoice(id=uuid.uuid4(), filename=f'{vendor}.pdf', file_path=f'/tmp/{vendor}.pdf', status='POSTED', vendor_name=vendor, invoice_date=entry_date, total=total, currency='USD')
    db.add(inv)
    db.flush()

    from app.models.chart_of_accounts import ChartOfAccount
    ap = db.query(ChartOfAccount).filter_by(account_code='2000').first()
    misc = db.query(ChartOfAccount).filter_by(account_code='7900').first()

    je = JournalEntry(
        id=uuid.uuid4(), invoice_id=inv.id, entry_date=entry_date, description=f'{vendor} bill',
        status=JournalEntryStatus.POSTED, entry_type=JournalEntryType.BILL,
        total_debit=total, total_credit=total,
    )
    je.lines.append(JournalEntryLines(account_id=misc.id, debit_amount=total, credit_amount=Decimal('0')))
    je.lines.append(JournalEntryLines(account_id=ap.id, debit_amount=Decimal('0'), credit_amount=total))
    db.add(je)
    db.commit()
    return inv.id

class TestPaymentRecording:
    def test_payment_created_entry(self, db):
        iid = _post_bill(db, vendor='Office Depot', total=Decimal('100.00'), entry_date=date(2026, 4, 1))
        csv = b'Date,Description,Amount\n2026-04-05,OFFICE DEPOT PURCHASE,-100.00\n'
        run_reconciliation(db, 'stmt.csv', csv)

        payment = db.query(JournalEntry).filter(JournalEntry.invoice_id==iid, JournalEntry.entry_type==JournalEntryType.PAYMENT).first()
        from app.models.chart_of_accounts import ChartOfAccount
        debit_line = [l for l in payment.lines if l.debit_amount > 0][0]
        credit_line = [l for l in payment.lines if l.credit_amount > 0][0]
        assert db.get(ChartOfAccount, debit_line.account_id).account_code == '2000'
        assert db.get(ChartOfAccount, credit_line.account_id).account_code == '1010'

    def test_rerunning_same_statement_does_not_duplicate_payment(self, db):
        iid = _post_bill(db, vendor='Acme Corp', total=Decimal('50.00'), entry_date=date(2026, 4, 1))
        csv = b'Date,Description,Amount\n2026-04-05,ACME CORP PYMT,-50.0\n'
        run_reconciliation(db, 'stmt.csv', csv)
        run_reconciliation(db, 'stmt.csv', csv)

        count = db.query(JournalEntry).filter(JournalEntry.invoice_id==iid, JournalEntry.entry_type==JournalEntryType.PAYMENT).count()
        assert count == 1

    def test_unmatched_payment_creates_no_payment_entry(self, db):
        _post_bill(db, vendor='CloudHost Solutions Inc.', total=Decimal('414.60'), entry_date=date(2026, 4, 15))
        csv = b'Date,Description,Amount\n2026-05-05,TOTALLY UNRELATED VENDOR,-999.00\n'
        run_reconciliation(db, 'stmt.csv', csv)

        payments = db.query(JournalEntry).filter(JournalEntry.entry_type == JournalEntryType.PAYMENT).count()
        assert payments == 0

    def test_bill_entry_endpoint_unaffected_by_payment_entry(self, db, client):
        iid = _post_bill(db, vendor='CloudHost Solutions Inc.', total=Decimal('414.60'),
                          entry_date=date(2026, 4, 15))
        csv = b"Date,Description,Amount\n2026-05-05,CLOUDHOST SOLUTIONS PYMT,-414.60\n"
        run_reconciliation(db, "stmt.csv", csv)

        r = client.get(f'/invoices/{iid}/journal-entry')
        assert r.status_code == 200
        assert r.json()['entry_type'] == 'BILL'

        r2 = client.get(f'/invoices/{iid}/payment-entry')
        assert r2.status_code == 200
        assert r2.json()['entry_type'] == 'PAYMENT'

    def test_payment_entry_endpoint_404_before_reconciliation(self, db, client):
        iid = _post_bill(db, vendor='CloudHost Solutions Inc.', total=Decimal('414.60'),
                          entry_date=date(2026, 4, 15))
        r = client.get(f'/invoices/{iid}/payment-entry')
        assert r.status_code == 404