"""Tests for the AP aging report: posted, but unpaid bills bucketed by how long they've been outstanding, with paid bills (those with a PAYMENT entry) excluded."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from app.models.chart_of_accounts import ChartOfAccount
from app.models.invoice import Invoice, InvoiceStatus
from app.models.journal_entry import JournalEntry, JournalEntryLines, JournalEntryStatus, JournalEntryType

def _bill(db, vendor, amount, days_ago, *, number='INV-1', posted=True):
    inv = Invoice(id=uuid.uuid4(), filename=f'{vendor}.pdf', file_path='/tmp/x.pdf', status=InvoiceStatus.POSTED, vendor_name=vendor, invoice_number=number,
                  total=amount, currency='USD', invoice_date=date.today() - timedelta(days=days_ago)
        )
    db.add(inv)
    db.flush()
    ap = db.query(ChartOfAccount).filter_by(account_code = '2000').first()
    exp = db.query(ChartOfAccount).filter_by(account_code = '7900').first()
    je = JournalEntry(id=uuid.uuid4(), invoice_id=inv.id, entry_date=date.today() - timedelta(days=days_ago), description=f'{vendor} bill',
                      entry_type=JournalEntryType.BILL, status=JournalEntryStatus.POSTED if posted else JournalEntryStatus.DRAFT,
                      total_debit=amount, total_credit=amount
    )
    je.lines.append(JournalEntryLines(account_id=exp.id, debit_amount=amount, credit_amount=Decimal('0')))
    je.lines.append(JournalEntryLines(account_id=ap.id, debit_amount=Decimal('0'), credit_amount=amount))
    db.add(je)
    db.commit()

    return inv, je

def _pay(db, invoice, amount):
    """Create a posted PAYMENT entry for an invoice."""
    ap = db.query(ChartOfAccount).filter_by(account_code = '2000').first()
    bank = db.query(ChartOfAccount).filter_by(account_code = '1010').first()
    je = JournalEntry(id=uuid.uuid4(), invoice_id=invoice.id, entry_date=date.today(), description=f'Payment {invoice.vendor_name}', entry_type=JournalEntryType.PAYMENT,
                      status=JournalEntryStatus.POSTED, total_debit=amount, total_credit=amount
    )
    je.lines.append(JournalEntryLines(account_id=ap.id, debit_amount=amount, credit_amount=Decimal('0')))
    je.lines.append(JournalEntryLines(account_id=bank.id, debit_amount=Decimal('0'), credit_amount=amount))
    db.add(je)
    db.commit()

    return je

class TestBucketing:
    def test_bills_land_in_correct_buckets(self, db, client):
        _bill(db, 'FreshVendor', Decimal('100'), days_ago=10, number='F-1')
        _bill(db, 'MidVendor', Decimal('200'), days_ago=45, number='M-1')
        _bill(db, 'OldVendor', Decimal('300'), days_ago=75, number='O-1')
        _bill(db, 'AncientVendor', Decimal('400'), days_ago=200, number='A-1')

        r = client.get('/reports/ap-aging')
        assert r.status_code == 200
        data = r.json()
        buckets = {b['bucket']: b for b in data['buckets']}
        assert buckets['0-30']['count'] == 1 and float(buckets['0-30']['total']) == 100.0
        assert buckets['31-60']['count'] == 1 and float(buckets['31-60']['total']) == 200.0
        assert buckets['61-90']['count'] == 1 and float(buckets['61-90']['total']) == 300.0
        assert buckets['90+']['count'] == 1 and float(buckets['90+']['total']) == 400.0
        assert float(data['total_outstanding']) == 1000.0

    def test_boundary_days_30_and_31(self, db, client):
        _bill(db, 'ExactlyThirty', Decimal('50'), days_ago=30, number='T-30')
        _bill(db, 'ThirtyOne', Decimal('60'), days_ago=31, number='T-31')
        r = client.get('/reports/ap-aging').json()
        buckets = {b['bucket']: b for b in r['buckets']}
        assert buckets['0-30']['count'] == 1
        assert buckets['31-60']['count'] == 1


class TestPaidExclusion:
    def test_paid_bill_excluded(self, db, client):
        inv, _ = _bill(db, 'PaidVendor', Decimal('100'), days_ago=40, number='P-1')
        _pay(db, inv, Decimal('100'))
        r = client.get('/reports/ap-aging').json()
        assert r['total_outstanding'] == '0' or float(r['total_outstanding']) == 0.0
        assert len(r['rows']) == 0

    def test_unpaid_bill_included_paid_excluded(self, db, client):
        inv_paid, _ = _bill(db, 'PaidVendor', Decimal('100'), days_ago=40, number='P-1')
        _pay(db, inv_paid, Decimal('100'))
        _bill(db, 'UnpaidVendor', Decimal('250'), days_ago=40, number='U-1')

        r = client.get('/reports/ap-aging').json()
        assert float(r['total_outstanding']) == 250.0
        vendors = {row['vendor_name'] for row in r['rows']}
        assert vendors == {'UnpaidVendor'}


class TestRowDetail:
    def test_row_has_days_and_bucket(self, db, client):
        _bill(db, 'SomeVendor', Decimal('100'), days_ago=45, number='S-1')
        r = client.get('/reports/ap-aging').json()
        assert len(r['rows']) == 1
        row = r['rows'][0]
        assert row['days_outstanding'] == 45
        assert row['bucket'] == '31-60'
        assert row['vendor_name'] == 'SomeVendor'
        assert row['invoice_number'] == 'S-1'

    def test_rows_sorted_most_overdue_first(self, db, client):
        _bill(db, 'Newer', Decimal('100'), days_ago=10, number='N-1')
        _bill(db, 'Older', Decimal('100'), days_ago=100, number='O-1')
        r = client.get('/reports/ap-aging').json()
        assert r['rows'][0]['vendor_name'] == 'Older'
        assert r['rows'][1]['vendor_name'] == 'Newer'


class TestDraftExcluded:
    def test_only_posted_bills_counted(self, db, client):
        _bill(db, 'DraftVendor', Decimal('100'), days_ago=40, number='D-1', posted=False)
        r = client.get('/reports/ap-aging').json()
        assert len(r['rows']) == 0


class TestEmpty:
    def test_no_bills_returns_empty_report(self, db, client):
        r = client.get('/reports/ap-aging').json()
        assert float(r['total_outstanding']) == 0.0
        assert all(b['count'] == 0 for b in r['buckets'])
        assert len(r['buckets']) == 4