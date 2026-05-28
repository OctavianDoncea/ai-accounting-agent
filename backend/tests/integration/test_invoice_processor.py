import uuid
from app.models.agent_log import AgentLog
from app.models.invoice import Invoice, InvoiceStatus
from app.models.journal_entry import JournalEntry, JournalEntryStatus
from app.services import invoice_processor
from tests.conftest import cloudhost_classification_response, cloudhost_extract_response

def _post_cloudhost(db, mock_llm) -> uuid.UUID:
    mock_llm['extraction'].chat_json.return_value = cloudhost_extract_response()
    mock_llm['classification'].chat_json.return_value = cloudhost_classification_response()
    inv = Invoice(id=uuid.uuid4(), filename='invoice_cloudhost.pdf', file_path='samples/invoice_cloudhost.pdf', status=InvoiceStatus.PENDING)
    db.add(inv)
    db.commit()
    iid = inv.id
    invoice_processor.process_invoice(iid)
    
    return iid

class TestFullPipeline:
    def test_happy_path_posts(self, db, mock_llm):
        iid = _post_cloudhost(db, mock_llm)
        db = db.bind.connect()
    
    def test_happy_path_produces_posted_invoice_and_journal_entry(self, db, mock_llm):
        iid = _post_cloudhost(db, mock_llm)

        from app.database import SessionLocal
        s = SessionLocal()
        inv = s.get(Invoice, iid)
        je = s.query(JournalEntry).filter(JournalEntry.invoice_id == iid).first()
        assert inv.status == InvoiceStatus.POSTED
        assert je is not None
        assert je.status == JournalEntryStatus.POSTED
        assert je.total_debit == je.total_credit

        logs = s.query(AgentLog).filter(AgentLog.invoice_id == iid).all()
        step_names = {l.step_name for l in logs}
        assert 'extract_text' in step_names
        assert 'extract_fields' in step_names
        assert 'check_duplicate' in step_names
        assert 'classify_line_items' in step_names
        assert 'build_entry' in step_names
        assert 'validate_entry' in step_names
        assert 'final_status' in step_names
        s.close()


class TestReviewPaths:
    def test_low_extraction_confidence_routes_to_review(self, db, mock_llm):
        resp = cloudhost_extract_response()
        resp['confidence'] = 0.3
        mock_llm['extraction'].chat_json.return_value = resp
        mock_llm['classification'].chat_json.return_value = cloudhost_classification_response()
        inv = Invoice(id=uuid.uuid4(), filename='invoice_cloudhost.pdf', file_path='/samples/invoice_cloudhost.pdf', status=InvoiceStatus.PENDING)
        db.add(inv)
        db.commit()
        iid = inv.id
        db.close()
        invoice_processor.process_invoice(iid)

        from app.database import SessionLocal
        s = SessionLocal()
        inv = s.get(Invoice, iid)
        assert inv.status == InvoiceStatus.NEEDS_REVIEW
        assert s.query(JournalEntry).filter(JournalEntry.invoice_id == iid).first() is None
        s.close()

    def test_missing_vendor_routes_to_review(self, db, mock_llm):
        resp = cloudhost_extract_response()
        resp['vendor_name'] = None
        mock_llm['extraction'].chat_json.return_value = resp
        mock_llm['classification'].chat_json.return_value = cloudhost_classification_response()

        inv = Invoice(id=uuid.uuid4(), filename='x.pdf', file_path='/samples/invoice_cloudhost.pdf', status=InvoiceStatus.PENDING)
        db.add(inv)
        db.commit()
        iid = inv.id
        db.close()
        invoice_processor.process_invoice(iid)

        from app.database import SessionLocal
        s = SessionLocal()
        inv = s.get(Invoice, iid)
        assert inv.status == InvoiceStatus.NEEDS_REVIEW
        s.close()

    def test_imbalance_routes_to_review_with_draft_entry(self, db, mock_llm):
        resp = cloudhost_extract_response()
        resp['total'] = 9999.99
        mock_llm['extraction'].chat_json.return_value = resp
        mock_llm['classification'].chat_json.return_value = cloudhost_classification_response()

        inv = Invoice(id=uuid.uuid4(), filename='x.pdf', file_path='/samples/invoice_cloudhost.pdf', status=InvoiceStatus.PENDING)
        db.add(inv)
        db.commit()
        iid = inv.id
        db.close()
        invoice_processor.process_invoice(iid)

        from app.database import SessionLocal
        s = SessionLocal()
        inv = s.get(Invoice, iid)
        je = s.query(JournalEntry).filter(JournalEntry.invoice_id == iid).first()
        assert inv.status == InvoiceStatus.NEEDS_REVIEW
        assert je is not None and je.status == JournalEntryStatus.DRAFT
        s.close()

    def test_invalid_account_code_fallback_routes_to_review(self, db, mock_llm):
        mock_llm['extraction'].chat_json.return_value = cloudhost_extract_response()
        bad = cloudhost_classification_response()
        bad['classifications'][0]['account_code'] = '9999'
        mock_llm['classification'].chat_json.return_value = bad

        inv = Invoice(id=uuid.uuid4(), filename='x.pdf', file_path='/samples/invoice_cloudhost.pdf', status=InvoiceStatus.PENDING)
        db.add(inv)
        db.commit()
        iid = inv.id
        db.close()
        invoice_processor.process_invoice(iid)

        from app.database import SessionLocal
        s = SessionLocal()
        inv = s.get(Invoice, iid)
        assert inv.status == InvoiceStatus.NEEDS_REVIEW
        s.close()


class TestDuplicate:
    def test_second_upload_of_same_invoice_is_flagged_duplicate(self, db, mock_llm):
        _post_cloudhost(db, mock_llm)
 
        from app.database import SessionLocal
        s = SessionLocal()
        # Now upload the same one again
        inv2 = Invoice(id=uuid.uuid4(), filename="invoice_cloudhost.pdf",
                       file_path="/samples/invoice_cloudhost.pdf",
                       status=InvoiceStatus.PENDING)
        s.add(inv2); s.commit(); iid2 = inv2.id
        s.close()
        invoice_processor.process_invoice(iid2)
 
        s = SessionLocal()
        inv2 = s.get(Invoice, iid2)
        assert inv2.status == InvoiceStatus.DUPLICATE
        # No journal entry for the duplicate
        assert s.query(JournalEntry).filter(JournalEntry.invoice_id == iid2).first() is None
        s.close()