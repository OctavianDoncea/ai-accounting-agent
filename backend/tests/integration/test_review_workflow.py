"""Tests for the human-in-the-loop review workflow"""
from app.services.review_service import ReviewError, submit_review
from app.schemas.review import LineOverride
from app.models.invoice import Invoice, InvoiceStatus
from app.models.journal_entry import JournalEntry, JournalEntryStatus, JournalEntryType
from tests.conftest import make_extracted_invoice


def _line_override(inv: Invoice, account_code: str) -> LineOverride:
    return LineOverride(line_id=inv.line_items[0].id, account_code=account_code)


class TestSubmitReview:
    def test_rejects_invoice_not_in_review_state(self, db):
        inv = make_extracted_invoice(db)
        inv.status = InvoiceStatus.POSTED
        db.commit()
        try:
            submit_review(db, inv.id, [_line_override(inv, '6300')], None)
            assert False, 'should have raised ReviewError'
        except ReviewError as e:
            assert 'NEEDS_REVIEW' in str(e)

    def test_rejects_nonexistent_invoice(self, db):
        import uuid
        try:
            submit_review(db, uuid.uuid4(), [LineOverride(line_id=1, account_code='6300')], None)
            assert False, 'should have raised ReviewError'
        except ReviewError as e:
            assert 'not found' in str(e).lower()

    def test_rejects_empty_overrides(self, db):
        inv = make_extracted_invoice(db)
        inv.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()
        try:
            submit_review(db, inv.id, [], None)
            assert False, 'should have raised ReviewError'
        except ReviewError as e:
            pass

    def test_valid_review_posts_balanced_entry(self, db):
        from decimal import Decimal
        inv = make_extracted_invoice(db, total=Decimal('100.00'), tax=None, line_items=[('Office chair', Decimal('100.00'))])
        inv.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()

        invoice, entry, validation = submit_review(db, inv.id, [_line_override(inv, '1500')], None)

        assert validation.is_valid is True
        assert invoice.status == InvoiceStatus.POSTED
        assert entry.status == JournalEntryStatus.POSTED
        assert entry.entry_type == JournalEntryType.BILL
        assert entry.total_debit == entry.total_credit == Decimal('100.00')

    def test_review_with_tax_account(self, db):
        from decimal import Decimal
        inv = make_extracted_invoice(db, total=Decimal('100.00'), tax=Decimal('8.00'), line_items=[('Widget', Decimal('92.00'))])
        inv.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()

        invoice, entry, validation = submit_review(db, inv.id, [_line_override(inv, '6300')], tax_account_code='6920')
        assert validation.is_valid is True
        assert len(entry.lines) == 3

    def test_invalid_account_code_keeps_invoice_in_review(self, db):
        from decimal import Decimal
        inv = make_extracted_invoice(db, total=Decimal('100.00'), line_items=[('Item', Decimal('100.00'))])
        inv.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()

        invoice, entry, validation = submit_review(db, inv.id, [_line_override(inv, '9999')], None)
        assert validation.is_valid is True
        from app.models.chart_of_accounts import ChartOfAccount
        debit_lines = [l for l in entry.lines if l.debit_amount > 0][0]
        assert db.get(ChartOfAccount, debit_lines.account_id).account_code == '7900'

    def test_replace_prior_drft_entry_not_payment_entry(self, db):
        from decimal import Decimal
        import uuid
        from app.models.journal_entry import JournalEntryLines
        from app.models.chart_of_accounts import ChartOfAccount

        inv = make_extracted_invoice(db, total=Decimal('100.00'), line_items=[('Item', Decimal('100.00'))])
        inv.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()

        ap = db.query(ChartOfAccount).filter_by(account_code='2000').first()
        bank = db.query(ChartOfAccount).filter_by(account_code='1010').first()
        payment = JournalEntry(id=uuid.uuid4(), invoice_id=inv.id, entry_date=inv.invoice_date, description='payment',
            status=JournalEntryStatus.POSTED, entry_type=JournalEntryType.PAYMENT,
            total_debit=Decimal('100.00'), total_credit=Decimal('100.00'))
        payment.lines.append(JournalEntryLines(account_id=ap.id, debit_amount=Decimal('100.00'), credit_amount=Decimal('0')))
        payment.lines.append(JournalEntryLines(account_id=bank.id, debit_amount=Decimal('0'), credit_amount=Decimal('100.00')))
        db.add(payment)
        db.commit()
        payment_id = payment.id

        submit_review(db, inv.id, [_line_override(inv, '6300')], None)

        still_there = db.get(JournalEntry, payment_id)
        assert still_there is not None
        assert still_there.entry_type == JournalEntryType.PAYMENT


class TestReviewAPI:
    def test_get_review_detail_for_needs_review_invoice(self, db, client):
        from decimal import Decimal
        inv = make_extracted_invoice(db, total=Decimal('50.00'), line_items=[('Thing', Decimal('50.00'))])
        inv.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()

        r = client.get(f'/invoices/{inv.id}/review')
        assert r.status_code == 200
        body = r.json()
        assert len(body['line_items']) == 1
        assert 'line_id' in body['line_items'][0]
        assert len(body["classifiable_accounts"]) > 0
        assert body['status'] == 'NEEDS_REVIEW'

    def test_get_review_detail_404_for_missing_invoice(self, client):
        import uuid
        r = client.get(f'/invoices/{uuid.uuid4()}/review')
        assert r.status_code == 404

    def test_post_review_posts_invoice(self, db, client):
        from decimal import Decimal
        inv = make_extracted_invoice(db, total=Decimal('50.00'), line_items=[('Thing', Decimal('50.00'))])
        inv.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()

        r = client.post(
            f'/invoices/{inv.id}/review',
            json={'overrides': [{'line_id': inv.line_items[0].id, 'account_code': '6300'}], 'tax_account_code': None},
        )
        assert r.status_code == 200
        body = r.json()
        assert body['invoice_status'] == 'POSTED'
        assert body['is_balanced'] is True

    def test_post_review_400_for_non_review_invoice(self, db, client):
        from decimal import Decimal
        inv = make_extracted_invoice(db, total=Decimal('50.00'), line_items=[('Thing', Decimal('50.00'))])
        inv.status = InvoiceStatus.POSTED
        db.commit()

        r = client.post(
            f'/invoices/{inv.id}/review',
            json={'overrides': [{'line_id': inv.line_items[0].id, 'account_code': '6300'}]},
        )
        assert r.status_code == 400

    def test_post_review_400_for_empty_overrides(self, db, client):
        from decimal import Decimal
        inv = make_extracted_invoice(db, total=Decimal('50.00'), line_items=[('Thing', Decimal('50.00'))])
        inv.status = InvoiceStatus.NEEDS_REVIEW
        db.commit()

        r = client.post(f'/invoices/{inv.id}/review', json={'overrides': []})
        assert r.status_code == 400
