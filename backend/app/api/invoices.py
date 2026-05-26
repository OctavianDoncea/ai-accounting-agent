import logging
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, UploadFile
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.models.agent_log import AgentLog
from app.models.invoice import Invoice, InvoiceStatus
from app.models.journal_entry import JournalEntry
from app.schemas.invoice import InvoiceOut, AgentLogOut, InvoiceSummaryOut, UploadResponse
from app.schemas.journal_entry import JournalEntryOut
from app.api.journal_entries import _serialize as serialize_journal_entry
from app.services.invoice_processor import reclassify_invoice, process_invoice

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
    entry = db.query(JournalEntry).filter(JournalEntry.invoice_id == invoice_id).order_by(JournalEntry.entry_date.desc()).first()
    if entry is None:
        raise HTTPException(status_code=404, detail='No journal entry for this invoice yet.')
    return serialize_journal_entry(db, entry)

@router.post('/{invoice_id}/reclassify', response_model=UploadResponse)
def reclassify(invoice_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> UploadResponse:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail='Invoice not found.')
    background_tasks.add_task(reclassify_invoice, invoice_id)
    return UploadResponse(invoice_id=invoice_id, status=InvoiceStatus.PENDING, message='Reclassification started.')