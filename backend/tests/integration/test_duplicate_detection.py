import uuid
from datetime import date
from decimal import Decimal
from app.models.invoice import Invoice, InvoiceStatus
from app.services.duplicate_detection import find_duplicate

def _invoice(db, *, vendor: str, number: str | None = None, total: Decimal | None = None, inv_date: date | None = None, status: InvoiceStatus = InvoiceStatus.EXTRACTED) -> Invoice:
    inv = Invoice(id=uuid.uuid4(), filename=f'{vendor}.pdf', file_path=f'/tmp/{vendor}.pdf', status=status, vendor_name=vendor, invoice_number=number, total=total, invoice_date=inv_date)
    db.add(inv)
    db.commit()

    return inv

class TestDuplicateDetection:
    def test_no_duplicates_returns_none(self, db):
        new = _invoice(db, vendor="CloudHost", number="CH-1", total=Decimal("100"),
                       inv_date=date(2026, 4, 15))
        assert find_duplicate(db, new) is None
 
    def test_same_vendor_and_number_is_duplicate(self, db):
        existing = _invoice(db, vendor="CloudHost", number="CH-1", total=Decimal("100"),
                            inv_date=date(2026, 4, 15))
        new = _invoice(db, vendor="CloudHost", number="CH-1", total=Decimal("100"),
                       inv_date=date(2026, 4, 15))
        match = find_duplicate(db, new)
        assert match is not None
        assert match.id == existing.id
 
    def test_vendor_case_insensitive(self, db):
        existing = _invoice(db, vendor="CloudHost Solutions", number="CH-1")
        new = _invoice(db, vendor="cloudhost solutions", number="CH-1")
        assert find_duplicate(db, new) is not None
 
    def test_same_vendor_total_and_close_date_is_duplicate(self, db):
        existing = _invoice(db, vendor="Acme", number=None, total=Decimal("250.00"),
                            inv_date=date(2026, 4, 15))
        new = _invoice(db, vendor="Acme", number=None, total=Decimal("250.00"),
                       inv_date=date(2026, 4, 16))  # 1 day apart
        assert find_duplicate(db, new) is not None
 
    def test_dates_too_far_apart_not_duplicate(self, db):
        _invoice(db, vendor="Acme", total=Decimal("250"), inv_date=date(2026, 4, 1))
        new = _invoice(db, vendor="Acme", total=Decimal("250"), inv_date=date(2026, 5, 1))
        assert find_duplicate(db, new) is None
 
    def test_different_total_not_duplicate(self, db):
        _invoice(db, vendor="Acme", total=Decimal("250"), inv_date=date(2026, 4, 15))
        new = _invoice(db, vendor="Acme", total=Decimal("260"), inv_date=date(2026, 4, 15))
        assert find_duplicate(db, new) is None
 
    def test_self_match_excluded(self, db):
        inv = _invoice(db, vendor="Acme", number="X", total=Decimal("100"),
                       inv_date=date(2026, 4, 15))
        assert find_duplicate(db, inv) is None
 
    def test_existing_duplicate_status_is_ignored(self, db):
        # An invoice already flagged DUPLICATE shouldn't match a new one
        _invoice(db, vendor="Acme", number="X", total=Decimal("100"),
                 inv_date=date(2026, 4, 15), status=InvoiceStatus.DUPLICATE)
        new = _invoice(db, vendor="Acme", number="X", total=Decimal("100"),
                       inv_date=date(2026, 4, 15))
        assert find_duplicate(db, new) is None