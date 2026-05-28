import uuid
from datetime import date
from decimal import Decimal
from app.agents.reconciliation_agent import reconcile, JournalEntryCandidate, _date_in_window, name_similarity, _normalize_tokens
from app.models.bank_transaction import BankTransaction, BankTransactionStatus, TransactionDirection

class TestNormalizeTokens:
    def test_strips_punctuation_and_lowercases(self):
        assert 'cloudhost' in _normalize_tokens('CloudHost, Inc.')

    def test_removes_noise_tokens(self):
        tokens = _normalize_tokens('CLOUDHOST SOLUTIONS PYMT ACH INC')
        assert 'pymt' not in tokens
        assert 'inc' not in tokens
        assert 'ach' not in tokens
        assert 'cloudhost' in tokens
        assert 'solutions' in tokens

    def test_removes_standalone_nuumbers(self):
        tokens = _normalize_tokens('OFFICE DEPOT #558 STORE 1234')
        assert '558' not in tokens
        assert '1234' not in tokens
        assert 'office' in tokens
        assert 'depot' in tokens

    def test_drops_short_tokens(self):
        tokens = _normalize_tokens('A B C cloudhost')
        assert tokens == {'cloudhost'}


class TestNameSimilarity:
    def test_exact_vendor_in_description_scores_one(self):
        score = name_similarity('CloudHost Solutions Inc.', 'CLOUDHOST SOLUTIONS PYMT ACH')
        assert score == 1.0

    def test_office_depot_matches_with_noise(self):
        score = name_similarity('Office Depot', 'OFFICE DEPOT #558 PURCHASE')
        assert score == 1.0

    def test_law_firm_matches_through_ach(self):
        score = name_similarity('Brightman & Associates LLP', 'BRIGHTMAN ASSOCIATES LLP ACH PMT')
        assert score == 1.0

    def test_unrelated_vendors_score_low(self):
        score = name_similarity('CloudHost Solutions Inc.', 'STARBUCKS STORE 4471')
        assert score < 0.3

    def test_empty_strings_score_zero(self):
        assert name_similarity('', 'anything') == 0.0
        assert name_similarity('vendor', '') == 0.0


class TestDateInWindow:
    def test_payment_after_invoice_is_in_window(self):
        assert _date_in_window(date(2026, 4, 15), date(2026, 5, 1)) is True

    def test_payment_slightly_before_invoice_is_in_window(self):
        assert _date_in_window(date(2026, 4, 10), date(2026, 4, 7)) is True

    def test_payment_to_far_after_is_out(self):
        assert _date_in_window(date(2026, 1, 1), date(2026, 6, 1)) is False

    def test_payment_long_before_is_out(self):
        assert _date_in_window(date(2026, 4, 10), date(2026, 4, 1)) is False

    def test_missing_dates_dont_exclude(self):
        assert _date_in_window(None, date(2026, 4, 1)) is True
        assert _date_in_window(date(2026, 4, 1), None) is True

def _txn(amount, description, txn_date=date(2026, 5, 5), direction=TransactionDirection.OUTFLOW) -> BankTransaction:
    return BankTransaction(
        run_id=uuid.uuid4(),
        transaction_date=txn_date,
        description=description,
        amount=Decimal(str(amount)),
        direction=direction,
    )

def _cand(amount, vendor, entry_date=date(2026, 4, 15)) -> JournalEntryCandidate:
    return JournalEntryCandidate(je_id=uuid.uuid4(), amount=Decimal(str(amount)), entry_date=entry_date, vendor_name=vendor)

class TestReconcile:
    def test_matches_amount_date_and_name(self):
        txns = [_txn(414.60, 'CLOUDHOST SOLUTIONS PYMT ACH')]
        cands = [_cand(414.60, 'CloudHost Solutions Inc.')]
        out = reconcile(txns, cands)
        assert len(out.matched) == 1
        assert out.matched[0][0].status == BankTransactionStatus.MATCHED
        assert out.matched[0][0].match_confidence == 1.0

    def test_unmatched_when_amounts_differ(self):
        txns = [_txn(500.00, 'CLOUDHOST SOLUTIONS')]
        cands = [_cand(414.60, 'CloudHost Solutions Inc.')]
        out = reconcile(txns, cands)
        assert out.matched() == []
        assert len(out.unmatched_transactions) == 1
        assert out.unmatched_transactions[0].status == BankTransactionStatus.UNMATCHED

    def test_unmatched_when_dates_too_far(self):
        txns = [_txn(414.60, 'CLOUDHOST', txn_date=date(2027, 1, 1))]
        cands = [_cand(414.60, 'CloudHost Solutions Inc.', entry_date=date(2026, 4, 15))]
        out = reconcile(txns, cands)
        assert out.matched() == []

    def test_inflows_are_generated(self):
        txns = [_txn(5000.00, 'PAYROLL DEPOSIT', direction=TransactionDirection.INFLOW)]
        cands = []
        out = reconcile(txns, cands)
        assert out.matched == []
        assert txns[0].status == BankTransactionStatus.IGNORED

    def test_candidate_consumed_only_once(self):
        txns = [_txn((100, 'ACME PYMT', _txn(100, 'ACME PYMT')))]
        cands = [_cand(100, 'Acme Corp')]
        out = reconcile(txns, cands)
        assert len(out.matched) == 1
        assert len(out.unmatched_candidates) == 1

    def test_unmatched_candidate_reported(self):
        txns = []
        cands = [_cand(414.60, 'CloudHost Solutions Inc.')]
        out = reconcile(txns, cands)
        assert len(out.unmatched_candidates) == 1

    def test_picks_best_name_match_when_amounts_tie(self):
        txns = [_txn(100), 'OFFICE DEPOT PURCHASE']
        cands = [_cand(100, 'Random Vendor Co', _cand(100, 'Office Depot'))]
        out = reconcile(txns, cands)
        assert len(out.matched) == 1
        assert out.matched[0][1].vendor_name == 'Office Depot'