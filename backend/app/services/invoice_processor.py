import logging
import uuid
from sqlalchemy.orm import Session
from app.agents.extraction_agent import ExtractionAgent
from app.agents.classification_agent import ClassificationAgent
from app.agents.validation_agents import validate_entry
from app.database import SessionLocal
from app.models.agent_log import AgentLogStatus
from app.models.chart_of_accounts import ChartOfAccount, AccountType
from app.models.invoice import Invoice, InvoiceLineItems, InvoiceStatus
from app.models.journal_entry import JournalEntry, JournalEntryStatus
from app.services import ocr
from app.services.agent_logger import time_step, write_log
from app.services.duplicate_detection import find_duplicate
from app.services.journal_entry_builder import build_journal_entry
from app.services.ollama_client import OllamaError

log = logging.getLogger(__name__)

CONFIDENCE_REVIEW_THRESHOLD = 0.6
CLASSIFICATION_POST_THRESHOLD = 0.7

def process_invoice(invoice_id: uuid.UUID) -> None:
    """Entry point for background processing. Owns its own DB session"""
    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        if invoice is None:
            log.error(f'process_invoice: invoice {invoice_id} not found')
            return
        _run_pipeline(db, invoice)
    except Exception:
        log.exception(f'Unhandled error processing invoice {invoice_id}')
    finally:
        db.close()

def _run_pipeline(db: Session, invoice: Invoice) -> None:
    # Step 1. OCR
    try:
        with time_step(db, invoice_id=invoice.id, agent_name='OCR', step_name='extract_text', input_data={'filename': invoice.filename}) as ctx:
            text, method = ocr.extract_text(invoice.file_path)
            invoice.raw_text = text
            db.add(invoice)
            db.commit()
            ctx['output_data'] = {'method': method, 'char_count': len(text)}
            ctx['reasoning'] = f'Extracted {len(text)} characters via {method}'
    except Exception as e:
        _fail(db, invoice, f'OCR failed: {e}')
        return

    # Step 2: Extraction Agent
    try:
        with time_step(db, invoice_id=invoice.id, agent_name='extraction_agent', step_name='extract_fields', input_data={'char_count': len(invoice.raw_text or '')}) as ctx:
            agent = ExtractionAgent()
            extracted = agent.extract(invoice.raw_text or '')

            invoice.vendor_name = extracted.vendor_name
            invoice.invoice_number = extracted.invoice_number
            invoice.invoice_date = extracted.invoice_date
            invoice.due_date = extracted.due_date
            invoice.subtotal = extracted.subtotal
            invoice.tax = extracted.tax
            invoice.total = extracted.total
            invoice.currency = extracted.currency or 'USD'

            invoice.line_items.clear()
            for li in extracted.line_items:
                invoice.line_items.append(InvoiceLineItems(
                    description=li.description,
                    quantity=li.quantity,
                    unit_price=li.unit_price,
                    amount=li.amount,
                ))
            db.add(invoice)
            db.commit()

            ctx['output_data'] = {
                'vendor_name': extracted.vendor_name,
                'total': float(extracted.total) if extracted.total is not None else None,
                'line_item_count': len(extracted.line_items)
            }
            ctx['reasoning'] = extracted.reasoning
            ctx['confidence_score'] = extracted.confidence
    except OllamaError as e:
        _fail(db, invoice, f'Extraction agent failed (is Ollama running?): {e}')
        return
    except Exception as e:
        _fail(db, invoice, f'Extraction agent failed: {e}')
        return

    # Step 3: Duplicate detection
    with time_step(db, invoice_id=invoice.id, agent_name='duplicate_detector', step_name='check_duplicate') as ctx:
        dup = find_duplicate(db, invoice)
        if dup is not None:
            invoice.status = InvoiceStatus.DUPLICATE
            db.add(invoice)
            db.commit()
            ctx['status'] = AgentLogStatus.FLAGGED
            ctx['output_data'] = {'duplicate_of': str(dup.id)}
            ctx['reasoning'] = (f'Matches existing invoice {dup.id} ({dup.vendor_name}, {dup.invoice_number}, total {dup.total}).')
            return
        ctx['output_data'] = {'duplicate': False}
        ctx['reasoning'] = 'No matching invoice found.'

    # Extraction-quality gate
    missing_critical = invoice.total is None or not invoice.vendor_name
    low_confidence = extracted.confidence < CONFIDENCE_REVIEW_THRESHOLD

    if missing_critical or low_confidence:
        invoice.status = InvoiceStatus.NEEDS_REVIEW
        reason = (
            'Missing critical fields (vendor or total)'
            if missing_critical
            else f'Low extraction confidence ({extracted.confidence:.2f})'
        )
        write_log(db, invoice_id=invoice.id, agent_name='pipeline', step_name='final_status', status=AgentLogStatus.FLAGGED, reasoning=reason, confidence_score=extracted.confidence)
        db.add(invoice)
        db.commit()
        return

    _classify_and_post(db, invoice)

def _fail(db: Session, invoice: Invoice, message: str) -> None:
    log.error(f'Invoice {invoice.id} failed: {message}')
    invoice.status = InvoiceStatus.FAILED
    invoice.error_message = message
    db.add(invoice)
    db.commit()

def reclassify_invoice(invoice_id: uuid.UUID) -> None:
    """Re-run only the classification + validation stage. Owns its own DB session, can be used as a backgrounbd task"""
    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        if invoice is None:
            log.error(f'reclassify_invoice: invoice {invoice_id} not found')
            return
        _classify_and_post(db, invoice)
    except Exception:
        log.exception(f'Unhandled error classifying invoice {invoice_id}')
    finally:
        db.close()

def _classifiable_accounts(db: Session) -> list[ChartOfAccount]:
    """Accounts the classifier may pick from: expenses, and (non-cash) assets"""
    excluded_codes = {'1000', '1010', '1020', '1100', '1510'} # cash/bank/AR/contra-asset
    return [
        a for a in db.query(ChartOfAccount).filter(
            ChartOfAccount.is_active.is_(True),
            ChartOfAccount.account_type.in_([AccountType.EXPENSE, AccountType.ASSET])
        )
        .order_by(ChartOfAccount.account_code)
        .all()
        if a.account_code not in excluded_codes
    ]

def _classify_and_post(db: Session, invoice: Invoice) -> None:
    existing = db.query(JournalEntry).filter(JournalEntry.invoice_id == invoice.id).all()
    for je in existing:
        db.delete(je)
    if existing:
        db.commit()

    # Step 4: Classification agent
    try:
        with time_step(db, invoice_id=invoice.id, agent_name='classification_agent', step_name='classify_line_items', input_data={'line_item_count': len(invoice.line_items)}) as ctx:
            accounts = _classifiable_accounts(db)
            agent = ClassificationAgent()
            result = agent.classify(invoice, accounts)
            ctx['output_data'] = {
                'classifications': [{'line_index': c.line_index, 'account_code': c.account_code, 'confidence': c.confidence} for c in result.classifications],
                'tax_account_code': result.tax_account_code,
            }
            ctx['reasoning'] = result.overall_reasoning
            ctx['confidence_score'] = result.min_confidence
    except OllamaError as e:
        _fail(db, invoice, f'Classification agent failed (is Ollama running?): {e}')
        return
    except Exception as e:
        _fail(db, invoice, f'Classification failed: {e}')
        return

    # Step 5: Build the journal entry (deterministic)
    builder_notes: list[str] = []
    try:
        with time_step(db, invoice_id=invoice.db, agent_name='journal_entry_builder', step_name='build_entry') as ctx:
            entry, notes = build_journal_entry(db, invoice, result)
            builder_notes = notes
            db.add(entry)
            db.commit()
            db.refresh(entry)
            ctx['output_data'] = {
                'journal_entry_id': str(entry.id),
                'total_debit': float(entry.total_debit),
                'total_credit': float(entry.total_credit),
                'line_count': len(entry.lines),
            }
            ctx['reasoning'] = '; '.join(notes) if notes else 'Built balanced double-entry from classified line items.'
            if notes:
                ctx['status'] = AgentLogStatus.FLAGGED
    except Exception as e:
        _fail(db, invoice, f'Journal entry construction failed: {e}')
        return

    # Step 6: Validation agent (deterministic)
    with time_step(db, invoice_id=invoice.id, agent_name='validation_agent', step_name='validate_entry') as ctx:
        validation = validate_entry(db, entry)
        ctx['output_data'] = {
            'is_valid': validation.is_valid,
            'errors': validation.errors,
            'warnings': validation.warnings,
        }
        ctx['reasoning'] = (
            'Entry is valid and balances.'
            if validation.is_valid
            else 'Validation failed: ' + '; '.join(validation.errors)
        )
        if not validation.is_valid:
            ctx['status'] = AgentLogStatus.FLAGGED

    # Step 7: Final status decision
    low_class_conf = result.min_confidence < CLASSIFICATION_POST_THRESHOLD
    had_fallback = len(builder_notes) > 0

    if validation.is_valid and not low_class_conf and not had_fallback:
        entry.status = JournalEntryStatus.POSTED
        invoice.status = InvoiceStatus.POSTED
        final_reason = 'Journal entry validated and posted.'
        final_status = AgentLogStatus.SUCCESS
    else:
        entry.status = JournalEntryStatus.DRAFT
        invoice.status = InvoiceStatus.NEEDS_REVIEW
        
        if not validation.is_valid:
            final_reason = 'Held for review: journal entry validation failed.'
        elif had_fallback:
            final_reason = 'Held for review: ' + ' '.join(builder_notes)
        else:
            final_reason = f'Held for review: low classification confidence ({result.min_confidence:.2f})'
        final_status = AgentLogStatus.FLAGGED

    db.add_all([entry, invoice])
    db.commit()

    write_log(db, invoice_id=invoice.id, agent_name='pipeline', step_name='final_status', status=final_status, reasoning=final_reason, confidence_score=result.min_confidence)