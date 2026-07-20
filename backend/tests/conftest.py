import os
import tempfile
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

# /app/uploads is Docker-only; use a writable dir for pytest (CI and local).
os.environ.setdefault('UPLOAD_DIR', tempfile.mkdtemp(prefix='test_uploads_'))

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.database import SessionLocal
from app.main import app
from app.models.invoice import Invoice, InvoiceStatus, InvoiceLineItems
from app.models.journal_entry import JournalEntry, JournalEntryStatus

# Database
TABLES_TO_TRUNCATE = ('bank_transactions', 'reconciliation_runs', 'journal_entry_lines', 'journal_entries', 'agent_logs', 'invoice_line_items', 'invoices')

SAMPLE_PDF = '/samples/invoice_cloudhost.pdf'
SAMPLE_OCR_TEXT = (
    'CloudHost Solutions Inc. Invoice CH-2026-00871 '
    'Cloud hosting Object storage Managed DB subtotal tax total 414.60'
)

@pytest.fixture(scope='session', autouse=True)
def _ensure_schema():
    """Apply migrations and seed before any test touches the DB."""
    command.upgrade(Config('alembic.ini'), 'head')
    from app.seed.run_seed import seed_chart_of_accounts
    seed_chart_of_accounts()

@pytest.fixture
def db():
    """Per-test DB session."""
    session = SessionLocal()
    session.execute(text(f"TRUNCATE {', '.join(TABLES_TO_TRUNCATE)} CASCADE"))
    session.commit()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client(db):
    return TestClient(app)

# LLM mocking
@pytest.fixture
def mock_ocr():
    with patch('app.services.invoice_processor.ocr.extract_text') as m:
        m.return_value = (SAMPLE_OCR_TEXT, 'pdf_text_layer')
        yield m

@pytest.fixture
def mock_llm():
    with patch('app.agents.extraction_agent.create_llm_client') as me, \
        patch('app.agents.classification_agent.create_llm_client') as mc:
        e_inst = MagicMock()
        c_inst = MagicMock()
        me.return_value = e_inst
        mc.return_value = c_inst
        yield {'extraction': e_inst, 'classification': c_inst}

# Domain factories
def cloudhost_extract_response() -> dict:
    return {
        'vendor_name': 'CloudHost Solutions Inc.',
        'invoice_number': 'CH-2026-00871',
        'invoice_date': '2026-04-15',
        'due_date': '2026-05-15',
        'currency': 'USD',
        'subtotal': 383.00,
        'tax': 31.60,
        'total': 414.60,
        'line_items': [
            {'description': 'Cloud hosting', 'quantity': 1, 'unit_price': 249.00, 'amount': 249.00},
            {'description': 'Object storage', 'quantity': 1, 'unit_price': 45.00, 'amount': 45.00},
            {'description': 'Managed DB', 'quantity': 1, 'unit_price': 89.00, 'amount': 89.00},
        ],
        'confidence': 0.95,
        'reasoning': 'Extracted from OCR with high confidence.'
    }

def cloudhost_classification_response() -> dict:
    return {
        'classifications': [
            {'line_index': 0, 'account_code': '6210', 'confidence': 0.95, 'reasoning': 'Cloud hosting'},
            {'line_index': 1, 'account_code': '6210', 'confidence': 0.92, 'reasoning': 'Object storage'},
            {'line_index': 2, 'account_code': '6210', 'confidence': 0.90, 'reasoning': 'Managed DB'},
        ],
        'tax_account_code': '6920',
        'overall_reasoning': 'All cloud infrastructure.'
    }

@pytest.fixture
def cloudhost_invoice(db):
    inv = Invoice(id=uuid.uuid4(), filename='invoice_cloudhost.pdf', file_path=SAMPLE_PDF, status=InvoiceStatus.PENDING)
    db.add(inv)
    db.commit()

    return inv

def make_extracted_invoice(db, *, vendor: str = "Test Vendor Inc.", number: str = "INV-001", inv_date: date = date(2026, 4, 15), total: Decimal = Decimal("100.00"), tax: Decimal | None = None, line_items: list[tuple[str, Decimal]] | None = None) -> Invoice:
    if line_items is None:
        line_items = [('Test item', total)]
    inv = Invoice(
        id=uuid.uuid4(), filename='test.pdf', file_path='/tmp/test.pdf', status=InvoiceStatus.EXTRACTED, vendor_name=vendor,
        invoice_number=number, invoice_date=inv_date, currency='USD', total=total, tax=tax,
        subtotal=(total - (tax or Decimal('0'))) if total is not None else None,
    )
    for desc, amount in line_items:
        inv.line_items.append(InvoiceLineItems(description=desc, quantity=Decimal('1'), unit_price=amount, amount=amount))
    db.add(inv)
    db.commit()
    db.refresh(inv)

    return inv