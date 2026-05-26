import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from app.models.bank_transaction import BankTransaction, BankTransactionStatus, TransactionDirection

log = logging.getLogger(__name__)

AMOUNT_TOLERNACE = Decimal('0.01')
DATE_WINDOW_BEFORE = 5
DATE_WINDOW_AFTER = 120
NAME_MATCH_THRESHOLD = 0.30
MATCH_CONFIDENCE_FLOOR = 0.60

NOISE_TOKENS = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co", "company",
    "llp", "plc", "gmbh",
    "pymt", "pmt", "payment", "payments", "pay", "ach", "pos", "debit", "credit", "card",
    "purchase", "autopay", "bill", "billpay", "online", "web", "epay", "recurring",
    "subscription", "store", "the", "and",
}

@dataclass
class JournalEntryCandidate:
    je_id: object
    amount: Decimal
    entry_date: date | None
    vendor_name: str
    matched: bool = False

@dataclass
class ReconciliationOutcome:
    matched: list[tuple] = field(default_factory=list)
    unmatched_transactions: list = field(default_factory=list)
    unmatched_candidates: list = field(default_factory=list)


def _normalize_tokens(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\b\d+\b", " ", text)
    tokens = {t for t in text.split() if t and t not in NOISE_TOKENS and len(t) > 1}
    return tokens

def name_similarity(vendor: str, description: str) -> float:
    v_tokens = _normalize_tokens(vendor or '')
    d_tokens = _normalize_tokens(description or '')
    if not v_tokens or not d_tokens:
        return 0.0

    # If every token in the vendor name is also in the description, they are a perfect match
    if v_tokens <= d_tokens:
        return 1.0

    intersection = v_tokens & d_tokens
    union = v_tokens | d_tokens
    jaccard = len(intersection) / len(union) if union else 0.0

    seq = SequenceMatcher(None, ' '.join(sorted(v_tokens)), ' '.join(sorted(d_tokens))).ratio()
    return max(jaccard, seq)

def _date_in_window(entry_date: date | None, txn_date: date | None) -> bool:
    if entry_date is None or txn_date is None:
        return True
    delta = (txn_date - entry_date).days
    return -DATE_WINDOW_BEFORE <= delta <= DATE_WINDOW_AFTER

def reconcile(transactions: list[BankTransaction], candidates: list[JournalEntryCandidate]) -> ReconciliationOutcome:
    outcome = ReconciliationOutcome()

    for txn in transactions:
        if txn.direction != TransactionDirection.OUTFLOW:
            txn.status = BankTransactionStatus.IGNORED
            txn.match_reasoning = 'Inflow / deposit - not part of accounts-payable reconciliation.'
            continue

        best: JournalEntryCandidate | None = None
        best_score = -1.0
        for cand in candidates:
            if cand.matched:
                continue
            if abs(cand.amount - txn.amount) > AMOUNT_TOLERNACE:
                continue
            if not _date_in_window(cand.entry_date, txn.transaction_date):
                continue
            score = name_similarity(cand.vendor_name, txn.description)
            if score > best_score:
                best_score = score
                best = cand

        if best is not None and best_score >= NAME_MATCH_THRESHOLD:
            confidence = round(min(0.6 + 0.4 * best_score, 1.0), 2)
            reasoning = (
                f"Amount {txn.amount} matches journal entry for '{best.vendor_name}' "
                f"(name similarity: {best_score:.2f})"
            )
            best.matched = True
            txn.status = BankTransactionStatus.MATCHED
            txn.matched_journal_entry_id = best.je_id
            txn.match_confidence = confidence
            txn.match_reasoning = reasoning
            outcome.matched.append((txn, best, confidence, reasoning))
        else:
            txn.status = BankTransactionStatus.UNMATCHED
            if best is None:
                txn.match_reasoning = 'No journal entry with a matching amount and date.'
            else:
                txn.match_reasoning = (
                    'An amount match exists but the vendor name is too dissimilar '
                    f'(bast similarity: {best_score:.2f})'
                )
            outcome.unmatched_transactions.append(txn)

    outcome.unmatched_candidates = [cand for cand in candidates if not cand.matched]
    return outcome