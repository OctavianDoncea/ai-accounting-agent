import logging
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from app.agents.reconciliation_agent import reconcile, JournalEntryCandidate
from app.models.agent_log import AgentLogStatus
from app.models.bank_transaction import BankTransaction, ReconciliationRun
from app.models.invoice import Invoice
from app.models.journal_entry import JournalEntry, JournalEntryStatus
from app.services.agent_logger import write_log
from app.services.bank_statement_parser import parse_bank_statement

log = logging.getLogger(__name__)

def run_reconciliation(db: Session, filename: str, content: bytes) -> ReconciliationRun:
    """Parse a bank statement, match against postred journal emtries, persist a report."""
    parsed = parse_bank_statement(content)

    run = ReconciliationRun(filename=filename, bank_transaction_count=len(parsed))
    db.add(run)
    db.flush()

    transactions: list[BankTransaction] = []
    for p in parsed:
        txn = BankTransaction(
            run_id = run.id,
            transaction_date = p['transaction_date'],
            description = p['description'],
            amount = p['amount'],
            direction = p['direction'],
            raw_row = p['raw_row']
        )
        db.add(txn)
        transactions.append(txn)
    db.flush()

    candidates = _load_candidates(db)
    outcome = reconcile(transactions, candidates)

    matched_amount = sum((t.amount for t, *_ in outcome.matched), Decimal('0'))
    run.matched_count = len(outcome.matched)
    run.unmatched_bank_count = len(outcome.unmatched_transactions)
    run.unmatched_journal_count = len(outcome.unmatched_candidates)
    run.total_matched_amount = matched_amount
    run.summary = (
        f'{len(outcome.matched)} matched, '
        f'{len(outcome.unmatched_transactions)} unmatched payment(s), '
        f'{len(outcome.unmatched_candidates)} posted entr(y/ies) without a matching payment.'
    )

    db.add_all([run, *transactions])
    db.commit()
    db.refresh(run)

    write_log(
        db,
        invoice_id=None,
        agent_name='reconciliation_agent',
        step_name='reconcile_statement',
        status=AgentLogStatus.SUCCESS if run.unmatched_bank_count == 0 else AgentLogStatus.FLAGGED,
        output_data={
            'matched': run.matched_count,
            'unmatched_bank': run.unmatched_bank_count,
            'unmatched_journal': run.unmatched_journal_count,
            'total_matched_amount': float(run.total_matched_amount),
        },
        reasoning=run.summary,
    )
    return run

def _load_candidates(db: Session) -> list[JournalEntryCandidate]:
    rows = (
        db.query(JournalEntry, Invoice)
        .outerjoin(Invoice, JournalEntry.invoice_id == Invoice.id)
        .filter(JournalEntry.status == JournalEntryStatus.POSTED)
        .all()
    )
    candidates = []
    for je, inv in rows:
        vendor = (inv.vendor_name if inv and inv.vendor_name else je.description) or ''
        candidates.append(JournalEntryCandidate(je_id=je.id, amount=je.total_credit, entry_date=je.entry_date, vendor_name=vendor))

    return candidates