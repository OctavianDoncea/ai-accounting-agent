import logging
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from app.agents.reconciliation_agent import reconcile, JournalEntryCandidate
from app.agents.validation_agents import validate_entry
from app.models.agent_log import AgentLogStatus
from app.models.bank_transaction import BankTransaction, ReconciliationRun
from app.models.invoice import Invoice
from app.models.journal_entry import JournalEntry, JournalEntryStatus, JournalEntryType
from app.services.agent_logger import write_log
from app.services.bank_statement_parser import parse_bank_statement
from app.services.journal_entry_builder import build_payment_entry

log = logging.getLogger(__name__)

def run_reconciliation(db: Session, filename: str, content: bytes, user_id=None) -> ReconciliationRun:
    """Parse a bank statement, match against posted journal entries, persist a report."""
    parsed = parse_bank_statement(content)

    run = ReconciliationRun(filename=filename, bank_transaction_count=len(parsed), user_id=user_id)
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

    candidates = _load_candidates(db, user_id=user_id)
    outcome = reconcile(transactions, candidates)

    payment_recorded = 0
    payment_skipped_existing = 0
    for txn, candidate, confidence, reasoning in outcome.matched:
        result = _record_payment(db, candidate, txn.transaction_date)
        if result == 'recorded':
            payment_recorded += 1
        elif result == 'already_recorded':
            payment_skipped_existing += 1

    matched_amount = sum((t.amount for t, *_ in outcome.matched), Decimal('0'))
    run.matched_count = len(outcome.matched)
    run.unmatched_bank_count = len(outcome.unmatched_transactions)
    run.unmatched_journal_count = len(outcome.unmatched_candidates)
    run.total_matched_amount = matched_amount
    run.summary = (
        f'{len(outcome.matched)} matched ({payment_recorded} new payment entr(y/ies) recorded)'
        + (f', {payment_skipped_existing} already recorded' if payment_skipped_existing else '')
        + f'), {len(outcome.unmatched_transactions)} unmatched payment(s), '
        f'{len(outcome.unmatched_candidates)} posted entr(y/ies) without a matching payment.'
    )

    db.add_all([run, *transactions])
    db.commit()
    db.refresh(run)

    write_log(
        db,
        invoice_id=None,
        user_id=user_id,
        agent_name='reconciliation_agent',
        step_name='reconcile_statement',
        status=AgentLogStatus.SUCCESS if run.unmatched_bank_count == 0 else AgentLogStatus.FLAGGED,
        output_data={
            'matched': run.matched_count,
            'unmatched_bank': run.unmatched_bank_count,
            'unmatched_journal': run.unmatched_journal_count,
            'total_matched_amount': float(run.total_matched_amount),
            'payments_recorded': payment_recorded,
            'payments_already_recorded': payment_skipped_existing,
        },
        reasoning=run.summary,
    )
    return run

def _load_candidates(db: Session, user_id=None) -> list[JournalEntryCandidate]:
    query = (
        db.query(JournalEntry, Invoice)
        .outerjoin(Invoice, JournalEntry.invoice_id == Invoice.id)
        .filter(JournalEntry.status == JournalEntryStatus.POSTED, JournalEntry.entry_type == JournalEntryType.BILL)
    )
    if user_id is not None:
        query = query.filter(JournalEntry.user_id == user_id)
    rows = query.all()
    candidates = []
    for je, inv in rows:
        vendor = (inv.vendor_name if inv and inv.vendor_name else je.description) or ''
        candidates.append(JournalEntryCandidate(je_id=je.id, amount=je.total_credit, entry_date=je.entry_date, vendor_name=vendor, invoice_id=inv.id if inv else None))

    return candidates

def _record_payment(db: Session, candidate: JournalEntryCandidate, payment_date) -> str:
    """Create an post the payment journal entry for a matched bill"""
    if candidate.invoice_id is None:
        log.warning(f'Matched journal entry {candidate.je_id} has no linked invoice; skippig payment entry.')
        return 'skipped'

    existing_payment = (db.query(JournalEntry).filter(JournalEntry.invoice_id == candidate.invoice_id, JournalEntry.entry_type == JournalEntryType.PAYMENT).first())
    if existing_payment is not None:
        return 'already_recorded'

    invoice = db.get(Invoice, candidate.invoice_id)
    bill_entry = db.get(JournalEntry, candidate.je_id)
    if invoice is None or bill_entry is None:
        return 'skipped'

    payment_entry, notes = build_payment_entry(db, invoice, bill_entry, payment_date)
    db.add(payment_entry)
    db.flush()

    validation = validate_entry(db, payment_entry)
    if validation.is_valid:
        payment_entry.status = JournalEntryStatus.POSTED
    else:
        payment_entry.status = JournalEntryStatus.DRAFT
        notes.append(f'Validation failed: {"; ".join(validation.errors)}')
    
    db.add(payment_entry)
    db.flush()

    write_log(
        db,
        invoice_id = invoice.id,
        user_id = invoice.user_id,
        agent_name = 'reconciliation_agent',
        step_name = 'record_payment',
        status = AgentLogStatus.SUCCESS if validation.is_valid else AgentLogStatus.FLAGGED,
        confidence_score = 1.0,
        output_data = {'amount': float(payment_entry.total_credit), 'notes': notes},
        reasoning=(
            f'Payment of {payment_entry.total_credit} matched and posted; '
            f'Accounts Payable cleared for {invoice.vendor_name or "vendor"}.'
            if validation.is_valid
            else f'Payment entry built but failed validation: {"; ".join(validation.errors)}'
        )
    )
    return 'recorded'