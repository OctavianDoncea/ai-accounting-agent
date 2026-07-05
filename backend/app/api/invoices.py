import logging
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, UploadFile
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.models.agent_log import AgentLog
from app.models.invoice import Invoice, InvoiceStatus
from app.models.journal_entry import JournalEntry, JournalEntryType
from app.schemas.invoice import InvoiceOut, AgentLogOut, InvoiceSummaryOut, UploadResponse
from app.schemas.journal_entry import JournalEntryOut
from app.schemas.review import ClassifiableAccountOut, ReviewDetailOut, ReviewLineItemOut, ReviewSubmission, ReviewSubmitResponse
from app.api.journal_entries import _serialize as serialize_journal_entry
from app.agents.validation_agents import validate_entry
from app.services.invoice_processor import reclassify_invoice, process_invoice, _classifiable_accounts
from app.services.review_service import ReviewError, submit_review

router = APIRouter(prefix='/invoices', tags=['invoices'])
log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp'}
MAX_FILE_BYTES = 20 * 1024 * 1024 # 20 MB

@router.post('/upload', response_model=UploadResponse, status_code=201)
async def upload_invoice(background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadResponse:
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail='Uploaded file is empty.')
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail='File exceeds 20 MB limit.')

    # Persist file with a unique name to avoid collisions
    invoice_id = uuid.uuid4()
    os.makedirs(settings.upload_dir, exist_ok=True)
    stored_name = f'{invoice_id}{ext}'
    stored_path = os.path.join(settings.upload_dir, stored_name)

    with open(stored_path, 'wb') as f:
        f.write(contents)

    invoice = Invoice(id=invoice_id, filename=file.filename or stored_name, file_path=stored_path, status=InvoiceStatus.PENDING)
    db.add(invoice)
    db.commit()

    background_tasks.add_task(process_invoice, invoice_id)

    return (UploadResponse(invoice_id=invoice_id, status=InvoiceStatus.PENDING, message='Invoice uploaded. Processing started.'))

@router.get('', response_model=list[InvoiceSummaryOut])
def list_invoices(status: InvoiceStatus | None = None, limit: int = 100, db: Session = Depends(get_db)) -> list[Invoice]:
    query = db.query(Invoice)
    if status:
        query = query.filter(Invoice.status == status)
    return query.order_by(Invoice.upload_date.desc()).limit(limit).all()

@router.get('/{invoice_id}', response_model=InvoiceOut)
def get_invoice(invoice_id: uuid.UUID, db: Session = Depends(get_db)) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail='Invoice not found.')
    return invoice

@router.get('/{invoice_id}/logs', response_model=list[AgentLogOut])
def get_invoice_logs(invoice_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AgentLog]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail='Invoice not found.')
    return (db.query(AgentLog).filter(AgentLog.invoice_id == invoice_id).order_by(AgentLog.created_at.desc()).all())

@router.post('/{invoice_id}/reprocess', response_model=UploadResponse)
def reprocess_invoice(invoice_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> UploadResponse:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail='Invoice not found.')
    invoice.status = InvoiceStatus.PENDING
    invoice.error_message = None
    db.add(invoice)
    db.commit()

    background_tasks.add_task(process_invoice, invoice_id)
    return (UploadResponse(invoice_id=invoice_id, status=InvoiceStatus.PENDING, message='Reprocessing started.'))

@router.get('/{invoice_id}/journal_entry', response_model=JournalEntryOut)
def get_invoice_journal_entry(invoice_id: uuid.UUID, db: Session = Depends(get_db)) -> JournalEntryOut:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail='Invoice not found.')
    entry = db.query(JournalEntry).filter(JournalEntry.invoice_id == invoice_id, JournalEntry.entry_type == JournalEntryType.BILL).order_by(JournalEntry.entry_date.desc()).first()
    if entry is None:
        raise HTTPException(status_code=404, detail='No journal entry for this invoice yet.')
    return serialize_journal_entry(db, entry)

@router.get('/{invoice_id}/payment-entry', response_model=JournalEntryOut)
def get_invoice_payment_entry(invoice_id: uuid.UUID, db: Session = Depends(get_db)) -> JournalEntryOut:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail='Invoice not found.')
    entry = db.query(JournalEntry).filter(JournalEntry.invoice_id == invoice_id, JournalEntry.entry_type == JournalEntryType.PAYMENT).order_by(JournalEntry.entry_date.desc()).first()
    if entry is None:
        raise HTTPException(status_code=404, detail='No payment recorded for this invoice yet.')
    return serialize_journal_entry(db, entry)

@router.post('/{invoice_id}/reclassify', response_model=UploadResponse)
def reclassify(invoice_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> UploadResponse:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail='Invoice not found.')
    background_tasks.add_task(reclassify_invoice, invoice_id)
    return UploadResponse(invoice_id=invoice_id, status=InvoiceStatus.PENDING, message='Reclassification started.')

@router.get('/{invoice_id}/review', response_model=ReviewDetailOut)
def get_review_detail(invoice_id: uuid.UUID, db: Session = Depends(get_db)) -> ReviewDetailOut:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail='Invoice not found.')

    draft_entry = db.query(JournalEntry).filter(JournalEntry.invoice_id == invoice_id, JournalEntry.entry_type == JournalEntryType.BILL).order_by(JournalEntry.entry_date.desc()).first()

    current_codes: dict[int, str] = {}
    current_tax_codes: str | None = None
    validation_errors: list[str] = []
    if draft_entry is not None:
        from app.models.chart_of_accounts import ChartOfAccount

        account_lookup = {a.id: a for a in db.query(ChartOfAccount).all()}
        debit_lines = [l for l in draft_entry.lines if l.debit_amount > 0]
        n_items = len(invoice.line_items)

        for idx, line in enumerate(debit_lines):
            acct = account_lookup.get(line.account_id)
            if acct is None:
                continue
            if idx < n_items:
                current_codes[invoice.line_items[idx].id] = acct.account_code
            else:
                current_tax_codes = acct.account_code
        validation_errors = validate_entry(db, draft_entry).errors

    classifiable = [ClassifiableAccountOut(
        account_code=a.account_code, account_name=a.account_name, account_type=a.account_type.value
    ) for a in _classifiable_accounts(db)]

    line_items = [ReviewLineItemOut(
        line_id = li.id,
        description = li.description,
        quantity = float(li.quantity) if li.quantity is not None else None,
        unit_price = float(li.unit_price) if li.unit_price is not None else None,
        amount = float(li.amount),
        current_account_code = current_codes.get(li.id)
    ) for li in invoice.line_items]

    return ReviewDetailOut(
        invoice_id = str(invoice_id),
        filename = invoice.filename,
        vendor_name = invoice.vendor_name,
        invoice_number = invoice.invoice_number,
        total = float(invoice.total) if invoice.total is not None else None,
        tax = float(invoice.tax) if invoice.tax is not None else None,
        currency = invoice.currency or 'USD',
        status = invoice.status.value,
        line_items = line_items,
        current_tax_account_code = current_tax_codes,
        classifiable_accounts = classifiable,
        validation_errors = validation_errors,
    )

@router.post('/{invoice_id}/review', response_model=ReviewSubmitResponse)
def submit_review_endpoint(invoice_id: uuid.UUID, submission: ReviewSubmission, db: Session = Depends(get_db)) -> ReviewSubmitResponse:
    try:
        invoice, entry, validation = submit_review(db, invoice_id, submission.overrides, submission.tax_account_code)
    except ReviewError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ReviewSubmitResponse(
        invoice_id = str(invoice_id),
        invoice_status = invoice.status.value,
        journal_entry_status = entry.status.value,
        is_balanced = validation.is_balanced,
        validation_errors = validation.errors,
    )