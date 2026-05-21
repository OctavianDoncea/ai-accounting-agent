import logging
import os
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.invoice import Invoice, InvoiceStatus
from app.models.agent_log import AgentLog
from app.schemas.invoice import InvoiceOut, InvoiceSummaryOut, AgentLogOut, UploadResponse
from app.services.invoice_processor import process_invoice

router = APIRouter(prefix='/invoices', tags=['invoices'])
log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp'}
MAX_FILE_BYTES = 20 * 1024 * 1024

@router.post('/upload', response_model=UploadResponse, status_code=201)
async def upload_invoice(background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadResponse:
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail='Uploaded file is empty.')
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail='File size exceeds 20MB limit.')

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

    return UploadResponse(invoice_id=invoice.id, status=InvoiceStatus.PENDING, message='Upload successful. Processing in background...')

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
        raise HTTPException(status_code=404, detail=f'Invoice {invoice_id} not found')
    return invoice

@router.get('/{invoice_id}/logs', response_model=list[AgentLogOut])
def get_invoice_logs(invoice_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AgentLog]:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f'Invoice {invoice_id} not found')
    return (db.query(AgentLog).filter(AgentLog.invoide_id == invoice_id).order_by(AgentLog.created_at.asc()).all())

@router.post('/{invoice_id}/reprocess', response_model=UploadResponse)
def reprocess_invoice(invoice_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> UploadResponse:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail=f'Invoice {invoice_id} not found')

    invoice.status = InvoiceStatus.PENDING
    invoice.error_message = None
    db.add(invoice)
    db.commit()

    background_tasks.add_task(process_invoice, invoice_id)
    return UploadResponse(invoice_id=invoice.id, status=InvoiceStatus.PENDING, message='Reprocessing started...')