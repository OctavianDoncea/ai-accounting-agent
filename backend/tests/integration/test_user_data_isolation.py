import uuid
from backend.app.models import JournalEntryType
import jwt as pyjwt
import pytest
from datetime import date
from decimal import Decimal
from app.config import settings
from app.models.chart_of_accounts import ChartOfAccount
from app.models.invoice import Invoice, InvoiceStatus
from app.models.journal_entry import JournalEntry, JournalEntryStatus, JournalEntryLines

@pytest.fixture
def auth_enabled():
    settings.jwt_secret = 'isolation-test-secret'
    yield
    settings.jwt_secret = ''

@pytest.fixture
def two_users(client, auth_enabled):
    ra = client.post('/auth/signup', json={'email': 'test1@example.com', 'password': 'password123'})
    rb = client.post('/auth/signup', json={'email': 'test2@example.com', 'password': 'password123'})
    token_a, token_b = ra.json()['access_token'], rb.json()['access_token']
    payload_a = pyjwt.decode(token_a, settings.jwt_secret, algorithms=['HS256'])
    payload_b = pyjwt.decode(token_b, settings.jwt_secret, algorithms=['HS256'])
    return {
        'token_a': token_a, 'user_id_a': uuid.UUID(payload_a['sub']),
        'token_b': token_b, 'user_id_b': uuid.UUID(payload_b['sub']),
    }

def _auth(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}

def _make_invoice(db, user_id, vendor='Vendor', total=Decimal('100.00')) -> Invoice:
    inv = Invoice(id=uuid.uuid4(), filename=f'{vendor}.pdf', file_path=f'/tmp/{vendor}.pdf', status=InvoiceStatus.POSTED,
        vendor_name=vendor, total=total, currency='USD', invoice_date=date(2026, 4, 15), user_id=user_id)
    db.add(inv)
    db.commit()
    return inv

def _make_posted_bill(db, user_id, vendor='Vendor', total=Decimal('100.00')) -> tuple[Invoice, JournalEntry]:
    inv = _make_invoice(db, user_id, vendor, total)
    ap = db.query(ChartOfAccount).filter_by(account_code='2000').first()
    misc = db.query(ChartOfAccount).filter_by(account_code='7900').first()
    je = JournalEntry(id=uuid.uuid4(), invoice_id=inv.id, entry_date=inv.invoice_date, description=f'{vendor} bill',
        status=JournalEntryStatus.POSTED, entry_type=JournalEntryType.BILL, total_debit=total, total_credit=total, user_id=user_id)
    je.lines.append(JournalEntryLines(account_id=misc.id, debit_amount=total, credit_amount=Decimal('0')))
    je.lines.append(JournalEntryLines(account_id=ap.id, debit_amount=Decimal('0'), credit_amount=total))
    db.add(je)
    db.commit()
    db.refresh(je)
    return inv, je

class TestInvoiceIsolation:
    def test_list_only_shows_own_invoices(self, db, client, two_users):
        _make_invoice(db, two_users['user_id_a'], vendor='AliceVendor')
        _make_invoice(db, two_users['user_id_b'], vendor='BobVendor')

        r = client.get('/invoices', headers=_auth(two_users['token_a']))
        assert {inv['vendor_name'] for inv in r.json()} == {'AliceVendor'}

        r = client.get('/invoices', headers=_auth(two_users['token_b']))
        assert {inv['vendor_name'] for inv in r.json()} == {'BobVendor'}

    def test_get_by_id_404s_for_someone_elses_invoice(self, db, client, two_users):
        inv_a = _make_invoice(db, two_users['user_id_a'])

        assert client.get(f'/invoices/{inv_a.id}', headers=_auth(two_users['token_b'])).status_code == 404
        assert client.get(f'/invoices/{inv_a.id}', headers=_auth(two_users['token_a'])).status_code == 200

    def test_logs_404_for_someone_elses_invoice(self, db, client, two_users):
        inv_a = _make_invoice(db, two_users['user_id_a'])
        r = client.get(f'/invoices/{inv_a.id}/logs', headers=_auth(two_users['token_b']))
        assert r.status_code == 404

    def test_journal_entry_endpoint_404_for_someone_elses_invoice(self, db, client, two_users):
        inv_a, _ = _make_posted_bill(db, two_users['user_id_a'])
        assert client.get(f'/invoices/{inv_a.id}/journal-entry', headers=_auth(two_users['token_b'])).status_code == 404
        assert client.get(f'/invoices/{inv_a.id}/journal-entry', headers=_auth(two_users['token_a'])).status_code == 200

    def test_reprocess_404_for_someone_elses_invoice(self, db, client, two_users):
        inv_a = _make_invoice(db, two_users['user_id_a'])
        r = client.post(f'/invoices/{inv_a.id}/reprocess', headers=_auth(two_users['token_b']))
        assert r.status_code == 404

    def test_reclassify_404_for_someone_elses_invoice(self, db, client, two_users):
        inv_a = _make_invoice(db, two_users['user_id_a'])
        r = client.post(f'/invoices/{inv_a.id}/reclassify', headers=_auth(two_users['token_b']))
        assert r.status_code == 404


class TestJournalEntryIsolation:
    def test_list_only_shows__own_entries(self, db, client, two_users):
        _make_posted_bill(db, two_users['user_id_a'], vendor='AliceVendor', total=Decimal('50'))
        _make_posted_bill(db, two_users['user_id_b'], vendor='BobVendor', total=Decimal('75'))

        r = client.get('/journal-entries', headers=_auth(two_users['token_a']))
        assert {e['description'] for e in r.json()} == {'AliceVendor bill'}

    def test_get_by_id_404_for_someone_elses_entry(self, db, client, two_users):
        _, je_a = _make_posted_bill(db, two_users['user_id_a'])
        r = client.get(f'/journal-entries/{je_a.id}', headers=_auth(two_users['token_b']))
        assert r.status_code == 404
        r = client.get(f'/journal-entries/{je_a.id}', headers=_auth(two_users['token_a']))
        assert r.status_code == 200

    def test_export_only_includes_own_entries(self, db, client, two_users):
        _make_posted_bill(db, two_users['user_id_a'], vendor='AliceVendor', total=Decimal('50'))
        _make_posted_bill(db, two_users['user_id_b'], vendor='BobVendor', total=Decimal('75'))
        r = client.get('/journal-entries/export', headers=_auth(two_users['token_a']))
        assert b'AliceVendor' in r.content
        assert b'BobVendor' not in r.content


class TestReconciliationIsolation:
    def test_matching_only_considers_own_bills(self, db, client, two_users):
        _make_posted_bill(db, two_users['user_id_a'], vendor='CloudHost Solutions Inc.', total=Decimal('414.60'))
        csv = b'Date,Description,Amount\n2026-05-05,CLOUDHOST SOLUTIONS PYMT,-414.6\n'

        r = client.post('/reconciliation/upload', files={'file': ('stmt.csv', csv, 'text/csv')}, headers=_auth(two_users['token_a']))
        assert r.status_code == 201
        assert r.json()['matched_count'] == 1

        r2 = client.post('/reconciliation/upload', files={'file': ('stmt.csv', csv, 'text/csv')}, headers=_auth(two_users['token_b']))
        assert r2.status_code == 201
        assert r2.json()['matched_count'] == 0

    def test_list_only_shows_own_runs(self, db, client, two_users):
        csv = b'Date,Description,Amount\n2026-05-05,SOMETHING,-10.00\n'
        client.post('/reconciliation/upload', files={'file': ('a.csv', csv, 'text/csv')}, headers=_auth(two_users['token_a']))
        client.post('/reconciliation/upload', files={'file': ('b.csv', csv, 'text/csv')}, headers=_auth(two_users['token_b']))

        r = client.get('/reconciliation/runs', headers=_auth(two_users['token_a']))
        assert len(r.json()) == 1
        assert r.json()[0]['filename'] == 'a.csv'

    def test_run_get_by_id_404_for_someone_elses_run(self, db, client, two_users):
        csv = b'Date,Description,Amount\n2026-05-05,SOMETHING,-10.00\n'
        r = client.post('/reconciliation/upload', files={'file': ('stmt.csv', csv, 'text/csv')}, headers=_auth(two_users['token_a']))
        run_id = r.json()['id']
        r2 = client.get(f'/reconciliation/runs/{run_id}', headers=_auth(two_users['token_b']))
        assert r2.status_code == 404

    def test_run_export_404_for_someone_elses_run(self, db, client, two_users):
        csv = b'Date,Description,Amount\n2026-05-05,SOMETHING,-10.00\n'
        r = client.post('/reconciliation/upload', files={'file': ('stmt.csv', csv, 'text/csv')}, headers=_auth(two_users['token_a']))
        run_id = r.json()['id']
        r2 = client.get(f'/reconciliation/runs/{run_id}/export', headers=_auth(two_users['token_b']))
        assert r2.status_code == 404

    def test_unmatched_journal_in_report_scoped_to_run_owner(self, db, client, two_users):
        _make_posted_bill(db, two_users['user_id_a'], vendor='AliceUnpaidBill', total=Decimal('999.00'))
        csv = b'Date,Description,Amount\n2026-05-05,UNRELATED,-1.00\n'
        r = client.post('/reconciliation/upload', files={'file': ('stmt.csv', csv, 'text/csv')}, headers=_auth(two_users['token_b']))
        vendors_shown = {row['vendor_name'] for row in r.json()['unmatched_bills']}
        assert 'AliceUnpaidBill' not in vendors_shown

    
class TestDashboardIsolation:
    def test_summary_only_reflects_own_data(self, db, client, two_users):
        _make_invoice(db, two_users['user_id_a'])
        _make_invoice(db, two_users['user_id_a'])
        _make_invoice(db, two_users['user_id_b'])

        assert client.get('/dashboard/summary', headers=_auth(two_users['token_a'])).json()['invoice_count'] == 2
        assert client.get('/dashboard/summary', headers=_auth(two_users['token_b'])).json()['invoice_count'] == 1

    def test_recent_invoices_scoped_to_owner(self, db, client, two_users):
        _make_invoice(db, two_users['user_id_a'], vendor='AliceOnly')
        r = client.get('/dashboard/summary', headers=_auth(two_users['token_b']))
        vendors = {inv['vendor_name'] for inv in r.json()['recent_invoices']}
        assert 'AliceOnly' not in vendors


class TestReportsIsolation:
    def test_trial_balance_only_reflects_own_entries(self, db, client, two_users):
        _make_posted_bill(db, two_users['user_id_a'], vendor='AliceVendor', total=Decimal('100'))
        _make_posted_bill(db, two_users['user_id_b'], vendor='BobVendor', total=Decimal('200'))

        r_a = client.get('/reports/trial-balance', headers=_auth(two_users['token_a']))
        r_b = client.get('/reports/trial-balance', headers=_auth(two_users['token_b']))
        assert float(r_a.json()['total_debit']) == 100.0
        assert float(r_b.json()['total_debit']) == 200.0

    def test_expense_breakdown_only_reflects_own_entries(self, db, client, two_users):
        _make_posted_bill(db, two_users['user_id_a'], vendor='AliceVendor', total=Decimal('100'))

        r = client.get('/reports/expense-breakdown', headers=_auth(two_users['token_a']))
        assert sum(float(row['total']) for row in r.json()) == 100.0

        r = client.get('/reports/expense-breakdown', headers=_auth(two_users['token_b']))
        assert sum(float(row['total']) for row in r.json()) == 0.0


class TestDuplicateDetectionIsolation:
    def test_same_looking_invoice_from_different_owners_not_flagged(self, db, client, two_users):
        from app.services.duplicate_detection import find_duplicate

        _make_invoice(db, two_users['user_id_a'], vendor='SharedVendorName', total=Decimal('99.99'))
        new_from_b = Invoice(id=uuid.uuid4(), filename='x.pdf', file_path='/tmp/x.pdf', status=InvoiceStatus.EXTRACTED, vendor_name='SharedVendorName', total=Decimal('99.99'), invoice_date=date(2026, 4, 15), user_id=two_users['user_id_b'])
        db.add(new_from_b)
        db.commit()

        assert find_duplicate(db, new_from_b) is None


class TestReviewIsolation:
    def test_cannot_submit_review_for_someone_elses_invoice(self, db, client, two_users):
        inv_a = _make_invoice(db, two_users['user_id_a'])
        inv_a.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()

        r = client.post(f'/invoices/{inv_a.id}/review', json={'overrides': [{'line_index': 0, 'account_code': '6300'}]}, headers=_auth(two_users['token_b']))
        assert r.status_code == 400
        assert 'not found' in r.json()['detail'].lower()

    def test_get_review_detail_404_for_someone_elses_invoice(self, db, client, two_users):
        inv_a = _make_invoice(db, two_users['user_id_a'])
        inv_a.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()
        r = client.get(f'/invoices/{inv_a.id}/review', headers=_auth(two_users['token_b']))
        assert r.status_code == 404

    def test_owner_can_review_their_own_invoice(self, db, client, two_users):
        inv_a = _make_invoice(db, two_users['user_id_a'], total=Decimal('100.00'))
        inv_a.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()
        r = client.post(f'/invoices/{inv_a.id}/review', json={'overrides': [{'line_index': 0, 'account_code': '6300'}]}, headers=_auth(two_users['token_a']))
        assert r.status_code in (200, 400)
        if r.status_code == 400:
            assert 'not found' not in r.json()['detail'].lower()


class TestBaseAuthStillEnforced:
    def test_no_token_still_401s(self, client, auth_enabled):
        assert client.get('/invoices').status_code == 401


class TestAuthDisabledSharesEverything:
    def test_shows_invoices_regardless_of_owner(self, db, client):
        assert settings.jwt_secret == ''
        _make_invoice(db, None, vendor='Unowned')
        r = client.get('/invoices')
        assert 'Unowned' in {inv['vendor_name'] for inv in r.json()}