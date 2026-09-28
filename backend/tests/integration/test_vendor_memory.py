import uuid
from app.models.invoice import Invoice, InvoiceStatus
from app.models.journal_entry import JournalEntry, JournalEntryLines, JournalEntryStatus
from app.models.chart_of_accounts import  ChartOfAccount
from app.models.vendor_memory import VendorAccountMemory, normalize_vendor
from app.services import invoice_processor
from app.services.vendor_memory_service import preffered_account, record_post, vendor_stats
from tests.conftest import cloudhost_classification_response, cloudhost_extract_response

SAMPLE = 'samples/invoice_cloudhost.pdf'

_invoice_seq = 0

def _process(db, mock_llm, extract, classify) -> uuid.UUID:
    global _invoice_seq
    _invoice_seq += 1

    bump = _invoice_seq
    extract = {
        **extract,
        'invoice_number': f'CH-SEQ-{bump}',
        'invoice_date': f'{2020 + bump}-04-15'
    }
    mock_llm['extraction'].chat_json.return_value = extract
    mock_llm['classification'].chat_json.return_value = classify
    inv = Invoice(id=uuid.uuid4(), filename='invoice_cloudhost.pdf', file_path=SAMPLE, status=InvoiceStatus.PENDING)
    db.add(inv)
    db.commit()
    iid = inv.id
    db.close()
    invoice_processor.process_invoice(iid)

    return iid

def _debit_account_codes(db, invoice_id) -> list[str]:
    """Debit-side account codes for the invoice's line items, EXCLUDING the sales-tax line (always 6920)"""
    je = db.query(JournalEntry).filter(JournalEntry.invoice_id == invoice_id).first()
    lookup = {a.id: a.account_code for a in db.query(ChartOfAccount).all()}

    return [
        lookup[l.account_id] for l in je.lines
        if l.debit_amount and l.debit_amount > 0 and lookup[l.account_id] != '6920'
    ]

class TestNormalize:
    def test_case_and_whitespace_collapse(self):
        assert normalize_vendor(' CloudHost Inc.') == 'cloudhost inc.'
        assert normalize_vendor('CLOUDHOST INC. ') == 'cloudhost inc.'

    def test_none_is_empty(self):
        assert normalize_vendor(None) == ''


class TestRecording:
    def test_posting_records_vendor_memory(self, db, mock_llm):
        _process(db, mock_llm, cloudhost_extract_response(), cloudhost_classification_response())
        rows = db.query(VendorAccountMemory).all()
        assert len(rows) >= 1
        # All three CloudHost lines classified to 6210
        codes = {r.account_code for r in rows}
        assert '6210' in codes

    def test_second_post_reinforces_times_seen(self, db, mock_llm):
        _process(db, mock_llm, cloudhost_extract_response(), cloudhost_classification_response())
        _process(db, mock_llm, cloudhost_extract_response(), cloudhost_classification_response())
        row = db.query(VendorAccountMemory).filter(VendorAccountMemory.account_code == '6210').first()
        assert row.times_seen == 2


class TestApplication:
    def test_known_vendor_overrides_low_confidence_line(self, db, mock_llm):
        # Confident post
        _process(db, mock_llm, cloudhost_extract_response(), cloudhost_classification_response())
        
        # Same vendor, but now the LLM is now unsure and picks the wrong account with low confidence on every line
        unsure = {
            'classifications': [
                {'line_index': 0, 'account_code': '7900', 'confidence': 0.30, 'reasoning': 'unsure'},
                {'line_index': 1, 'account_code': '7900', 'confidence': 0.30, 'reasoning': 'unsure'},
                {'line_index': 2, 'account_code': '7900', 'confidence': 0.30, 'reasoning': 'unsure'},
            ],
            'tax_account_code': '6920',
            'overall_reasoning': 'unsure'
        }
        iid = _process(db, mock_llm, cloudhost_extract_response(), unsure)

        db.expire_all()
        inv = db.get(Invoice, iid)
        codes = _debit_account_codes(db, iid)
        assert all(c == '6210' for c in codes), f'expected all 6210, got{codes}'
        assert inv.status == InvoiceStatus.POSTED

    def test_high_confidence_lines_not_overriden(self, db, mock_llm):
        _process(db, mock_llm, cloudhost_extract_response(), cloudhost_classification_response())

        confident_diff = {
            'classifications': [
                {'line_index': 0, 'account_code': '6500', 'confidence': 0.97, 'reasoning': 'sure'},
                {'line_index': 1, 'account_code': '6500', 'confidence': 0.96, 'reasoning': 'sure'},
                {'line_index': 2, 'account_code': '6500', 'confidence': 0.95, 'reasoning': 'sure'}
            ],
            'tax_account_code': '6920',
            'overall_reasoning': 'confident'
        }
        iid = _process(db, mock_llm, cloudhost_extract_response(), confident_diff)
        db.expire_all()
        codes = _debit_account_codes(db, iid)
        assert all(c == '6500' for c in codes), f'confident LLM read should win, got {codes}'


class TestVendorStats:
    def test_stats_summarize_per_vendor(self, db, mock_llm):
        _process(db, mock_llm, cloudhost_extract_response(), cloudhost_classification_response())
        stats = vendor_stats(db, None)
        assert len(stats) == 1
        assert stats[0]['vendor'] == 'CloudHost Solutions Inc.'
        assert stats[0]['total_posts'] >= 1


class TestPrefferedAccountUnit:
    def test_returns_none_for_unknown_vendor(self, db):
        assert preffered_account(db, None, 'Never Seen Vendor') is None

    def test_returns_none_for_empty_vendor(self, db):
        assert preffered_account(db,None, None) is None