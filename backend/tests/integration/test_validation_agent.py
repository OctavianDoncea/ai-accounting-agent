import uuid
from decimal import Decimal
from datetime import date
from app.agents.validation_agents import validate_entry
from app.models.chart_of_accounts import ChartOfAccount
from app.models.journal_entry import JournalEntry, JournalEntryLines, JournalEntryStatus

def _make_entry(db, lines: list[tuple[str, Decimal, Decimal]]) -> JournalEntry:
    """Build a journal entry from (account_code, debit, credit) tuples"""
    accounts = {a.account_code: a for a in db.query(ChartOfAccount).all()}
    entry = JournalEntry(
        id=uuid.uuid4(),
        entry_date=date(2026, 4, 15),
        description='Test Entry',
        status=JournalEntryStatus.DRAFT,
        total_debit=sum((d for _, d, _ in lines), Decimal('0')),
        total_credit=sum((c for _, _, c in lines), Decimal('0'))
    )
    for code, debit, credit in lines:
        entry.lines.append(JournalEntryLines(account_id=accounts[code].id, debit_amount=debit, credit_amount=credit))
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return entry

class TestValidation:
    def test_balanced_entry_is_valid(self, db):
        entry = _make_entry(db, [('6300', Decimal('100'), Decimal('0')), ('2000', Decimal('0'), Decimal('100'))])
        result = validate_entry(db, entry)
        assert result.is_valid is True
        assert result.errors == []

    def test_imbalance_is_caught(self, db):
        entry = _make_entry(db, [('6300', Decimal('100'), Decimal('0')), ('2000', Decimal('0'), Decimal('90'))])
        result = validate_entry(db, entry)
        assert result.is_valid is False
        assert any('balance' in e.lower() for e in result.errors)

    def test_no_debit_lines_is_caught(self, db):
        entry = _make_entry(db, [('2000', Decimal('0'), Decimal('100')), ('4000', Decimal('0'), Decimal('100'))])
        result = validate_entry(db, entry)
        assert result.is_valid is False
        assert any('debit' in e.lower() for e in result.errors)

    def test_no_credit_lines_is_caught(self, db):
        entry = _make_entry(db, [('6300', Decimal('100'), Decimal('0')), ('6400', Decimal('0'), Decimal('0'))])
        result = validate_entry(db, entry)
        assert result.is_valid is False
        assert any('credit' in e.lower() for e in result.errors)

    def test_subcent_imbalance_within_tolerance_warns(self, db):
        entry = _make_entry(db, [('6300', Decimal('100.00'), Decimal('0')), ('2000', Decimal('0'), Decimal('100.01'))])
        result = validate_entry(db, entry)
        assert result.is_valid is True
        assert result.warnings != []

    def test_works_after_session_commit(self, db):
        entry = _make_entry(db, [('6300', Decimal('100'), Decimal('0')), ('2000', Decimal('0'), Decimal('100'))])
        db.commit()
        db.commit()
        result = validate_entry(db, entry)
        assert result.is_valid is True