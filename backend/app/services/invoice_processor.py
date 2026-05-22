import logging
import uuid
from sqlalchemy.orm import Session
from app.agents.extraction_agent import ExtractionAgent
from app.database import SessionLocal
from app.models.agent_log import AgentLogStatus
from app.models.invoice import Invoice, InvoiceStatus, InvoiceLineItems
from app.services import ocr
from app.services.agent_logger import write_log, time_step
from app.services.duplicate_detection import find_duplicate
from app.services.ollama_client import OllamaError

log = logging.getLogger(__name__)

# Below this confidence, or when critical fields are missing, route to human review.
CONFIDENCE_REVIEW_THRESHOLD = 0.6

def process_invoice(invoice_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        invoice = db.get(Invoice, invoice_id)
        if invoice is None:
            log.error(f'process_invoice: invoice {invoice_id} not found')
            return
        _run_pipeline(db, invoice)
    except Exception:
        log.exception(f'Unhandled error processing invoice {invoice_id}')
    finally: db.close()

def _run_pipeline(db: Session, invoice: Invoice) -> None:
    # Step 1: OCR
    try:
        with time_step(db, invoice_id=invoice.id, agent_name='ocr', step_name='extract_text', input_data={'filename': invoice.filename}) as ctx:
            text, method = ocr.extract_text(invoice.file_path)
            invoice.raw_text = text
            db.add(invoice)
            db.commit()
            ctx['output_data'] = {'method': method, 'char_count': len(text)}
            ctx['reasoning'] = f'Extracted {len(text)} characters via {method}.'
    except Exception as e:
        _fail(db, invoice.id, f'OCR failed: {e}')
        return

    # Step 2: Extraction agent
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
                invoice.line_items.append(
                    InvoiceLineItems(
                        description=li.description,
                        quantity=li.quantity,
                        unit_price=li.unit_price,
                        amount=li.amount,
                    )
                )
            db.add(invoice)
            db.commit()

            ctx['output_data'] = {
                'vendor_name': extracted.vendor_name,
                'total': float(extracted.total) if extracted.total is not None else None,
                'line_item_count': len(extracted.line_items)
            }
            ctx['reasoning'] = extracted.reasoning or 'Extraction completed successfully.'
            ctx['confidence_score'] = extracted.confidence
    except OllamaError as e:
        _fail(db, invoice.id, f'Extraction failed (is Ollama running?): {e}')
        return
    except Exception as e:
        _fail(db, invoice.id, f'Extraction failed: {e}')
        return

    # Step 3: Duplicate detection
    with time_step(db, invoice_id=invoice.id, agent_name='duplicate_detection', step_name='check_duplicate') as ctx:
        dup = find_duplicate(db, invoice)
        if dup is not None:
            invoice.status = InvoiceStatus.DUPLICATE
            db.add(invoice)
            db.commit()
            ctx['status'] = AgentLogStatus.FLAGGED
            ctx['output_data'] = {'duplicate_of': str(dup.id)}
            ctx['reasoning'] = (
                f'Matches existing invoice {dup.id} '
                f'({dup.vendor_name}, {dup.invoice_number}, total {dup.total})'
            )
            return
        ctx['output_data'] = {'duplicate': False}
        ctx['reasoning'] = 'No matching invoice found.'

    # Final status decision
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
    else:
        invoice.status = InvoiceStatus.EXTRACTED
        write_log(db, invoice_id=invoice.id, agent_name='pipeline', step_name='final_status', status=AgentLogStatus.SUCCESS, reasoning='Extraction successful.', confidence_score=extracted.confidence)
    db.add(invoice)
    db.commit()

def _fail(db: Session, invoice_id: uuid.UUID, message: str) -> None:
    log.error(f'Invoice {invoice_id} failed: {message}')
    db.rollback()
    invoice = db.get(Invoice, invoice_id)

    if invoice is None:
        return
    
    invoice.status = InvoiceStatus.FAILED
    invoice.error_message = message
    db.add(invoice)
    db.commit()