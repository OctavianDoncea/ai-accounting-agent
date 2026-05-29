from decimal import Decimal
from app.schemas.journal_entry import ClassificationResult, LineClassification
from app.services.journal_entry_builder import build_journal_entry
from tests.conftest import make_extracted_invoice

def _classification(line_codes: list[str], tax_code: str | None = '6920') -> ClassificationResult:
    return ClassificationResult(
        classifications=[
            LineClassification(line_index=i, account_code=c, confidence=0.9)
            for i, c in enumerate(line_codes)
        ],
        tax_account_code=tax_code,
    )

class TestBalancedConstruction:
    def test_simple_invoice_builds_balanced_entry(self, db):
        inv = make_extracted_invoice(db, total=Decimal('100.00'), tax=Decimal('8.00'), line_items=[('Item A', Decimal('92.00'))])
        entry, notes = build_journal_entry(db, inv, _classification(['6300']))
        assert notes == []
        assert entry.total_debit == Decimal('100.00')
        assert entry.total_credit == Decimal('100.00')
        debit_lines = [l for l in entry.lines if l.debit_amount > 0]
        credit_lines = [l for l in entry.lines if l.credit_amount > 0]
        assert len(debit_lines) == 2
        assert len(credit_lines) == 1

    def test_multi_item_invoice(self, db):
        inv = make_extracted_invoice(
            db, total=Decimal('383.00'), tax=None,
            line_items=[
                ('Cloud hosting', Decimal('249.00')),
                ('Storage', Decimal('45.00')),
                ('Database', Decimal('89.00'))
            ]
        )
        entry, notes = build_journal_entry(db, inv, _classification(['6210', '6210', '6210'], tax_code=None))
        assert entry.total_debit == Decimal('383.00')
        assert entry.total_credit == Decimal('383.00')
        assert len(entry.lines) == 4 # 3 items + 1 AP credit

    def test_no_tax_means_no_tax_line(self, db):
        inv = make_extracted_invoice(db, total=Decimal('100.00'), tax=Decimal('0'), line_items=[('Item', Decimal('100.00'))])
        entry, _ = build_journal_entry(db, inv, _classification(['6300']))
        assert len(entry.lines) == 2


class TestFallbacks:
    def test_invalid_account_code_falls_back_to_misc(self, db):
        inv = make_extracted_invoice(db, total=Decimal('100'), line_items=[('Item', Decimal('100'))])
        entry, notes = build_journal_entry(db, inv, _classification(['9999']))
        assert notes != []
        assert '7900' in notes[0]
        assert entry.total_debit == entry.total_credit

    def test_missing_total_uses_sum_of_debits(self, db):
        inv = make_extracted_invoice(db, total=None, line_items=[('Item', Decimal('50'))])
        inv.total = None
        db.commit()
        entry, notes = build_journal_entry(db, inv, _classification(['6300']))
        assert entry.total_debit == entry.total_credit
        assert any('total missing' in n.lower() for n in notes)


class TestAccountsPayableCredit:
    def test_credit_always_to_ap(self, db):
        inv = make_extracted_invoice(db, total=Decimal("100"))
        entry, _ = build_journal_entry(db, inv, _classification(["6300"]))
        credit_lines = [l for l in entry.lines if l.credit_amount > 0]
        assert len(credit_lines) == 1

        from app.models.chart_of_accounts import ChartOfAccount
        ap_acct = db.get(ChartOfAccount, credit_lines[0].account_id)
        assert ap_acct.account_code == "2000"