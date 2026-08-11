import logging
from sqlalchemy.orm import Session
from app.agents.validation_agents import validate_entry
from app.models.agent_log import AgentLogStatus
from app.models.invoice import Invoice, InvoiceStatus
from app.models.journal_entry import JournalEntry, JournalEntryStatus, JournalEntryType
from app.schemas.journal_entry import ClassificationResult, LineClassification, ValidationResult
from app.schemas.review import LineOverride
from app.services.agent_logger import write_log
from app.services.journal_entry_builder import build_journal_entry

log = logging.getLogger(__name__)

class ReviewError(ValueError):
    """Raised for invalid review submissions"""


def submit_review(db: Session, invoice_id, overrides: list[LineOverride], tax_account_code: str | None = None, requesting_user_id=None) -> tuple[Invoice, JournalEntry, ValidationResult]:
    """Apply a human reviewer's account choices, rebuild the journal entry"""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None or (requesting_user_id is not None and invoice.user_id != requesting_user_id):
        raise ReviewError('Invoice not found.')
    if invoice.status != InvoiceStatus.NEEDS_REVIEW:
        raise ReviewError(f'Invoice is "{invoice.status.value}", not NEEDS_REVIEW. Nothing to review.')
    if not overrides:
        raise ReviewError('At least one line item classification is required.')

    existing = db.query(JournalEntry).filter(JournalEntry.invoice_id == invoice_id, JournalEntry.entry_type == JournalEntryType.BILL).all()
    for je in existing:
        db.delete(je)
    if existing:
        db.commit()

    line_index_by_id = {li.id: i for i, li in enumerate(invoice.line_items)}
    for o in overrides:
        if o.line_id not in line_index_by_id:
            raise ReviewError(f'Line item {o.line_id} not found on this invoice.')

    classification = ClassificationResult(
        classifications = [
            LineClassification(line_index=line_index_by_id[o.line_id], account_code=o.account_code, confidence=1.0, reasoning='Manually approved by reviewer.')
            for o in overrides
        ],
        tax_account_code = tax_account_code,
        overall_reasoning='Manual review override.'
    )

    entry, notes = build_journal_entry(db, invoice, classification)
    entry.entry_type = JournalEntryType.BILL
    db.add(entry)
    db.flush()

    validation = validate_entry(db, entry)
    if validation.is_valid:
        entry.status = JournalEntryStatus.POSTED
        invoice.status = InvoiceStatus.POSTED
        invoice.error_message = None
    else:
        entry.status = JournalEntryStatus.DRAFT
        invoice.status = InvoiceStatus.NEEDS_REVIEW

    db.add_all([entry, invoice])
    db.commit()
    db.refresh(entry)
    db.refresh(invoice)

    write_log(
        db,
        invoice_id = invoice.id,
        user_id = invoice.user_id,
        agent_name = 'human_reviewer',
        step_name = 'manual_override',
        status = AgentLogStatus.SUCCESS if validation.is_valid else AgentLogStatus.FLAGGED,
        confidence_score = 1.0,
        output_data = {
            'overrides': [{'line_id': o.line_id, 'account_code': o.account_code} for o in overrides],
            'tax_account_code': tax_account_code,
            'builder_notes': notes
        },
        reasoning=(
            f'Reviewer classified {len(overrides)} line item(s); entry validated and posted.'
            if validation.is_valid
            else f'Reviewer classified {len(overrides)} line item(s) but entry failed validation: {"; ".join(validation.errors)}'
        )
    )

    return invoice, entry, validation