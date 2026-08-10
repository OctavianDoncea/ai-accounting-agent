import logging
import os
import uuid
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.bank_transaction import BankTransaction, BankTransactionStatus, ReconciliationRun
from app.models.invoice import Invoice
from app.models.journal_entry import JournalEntry, JournalEntryStatus
from app.schemas.reconciliation import BankTransactionOut, ReconciliationSummaryOut, ReconciliationRunOut, UnmatchedJournalEntryOut
from app.services.bank_statement_parser import BankStatementParseError
from app.services.reconciliation_processor import run_reconciliation
from app.security import get_current_user_id

router = APIRouter(prefix='/reconciliation', tags=['reconciliation'])
log = logging.getLogger(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024 # 10 MB

def _get_owned_run(db: Session, run_id: uuid.UUID, user_id: uuid.UUID | None = None) -> ReconciliationRun | None:
    query = db.query(ReconciliationRun).filter(ReconciliationRun.id == run_id)
    if user_id is not None:
        query = query.filter(ReconciliationRun.user_id == user_id)
    
    return query.first()

@router.post('/upload', response_model=ReconciliationSummaryOut, status_code=201)
async def upload_statement(file: UploadFile = File(...), db: Session = Depends(get_db), user_id: uuid.UUID | None = Depends(get_current_user_id)) -> ReconciliationSummaryOut:
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in {'.csv', '.txt'}:
        raise HTTPException(status_code=400, detail='Please upload a .csv bank statement.')

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail='Uploaded file is empty.')
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail='File exceeds 10 MB limit.')

    try:
        run = run_reconciliation(db, file.filename or 'statement.csv', contents, user_id=user_id)
    except BankStatementParseError as e:
        raise HTTPException(status_code=400, detail=f'Failed to parse bank statement: {e}')

    return _build_report(db, run)

@router.get('/runs', response_model=list[ReconciliationRunOut])
def list_runs(limit: int = 50, db: Session = Depends(get_db), user_id: uuid.UUID | None = Depends(get_current_user_id)) -> list[ReconciliationRunOut]:
    query = db.query(ReconciliationRun)
    if user_id is not None:
        query = query.filter(ReconciliationRun.user_id == user_id)
    return db.query(ReconciliationRun).order_by(ReconciliationRun.created_at.desc()).limit(limit).all()

@router.get('/runs/{run_id}/export')
def export_run(run_id: uuid.UUID, db: Session = Depends(get_db), user_id: uuid.UUID | None = Depends(get_current_user_id)) -> Response:
    """Export a reconciliation run as CSV (one row per matched transaction)."""
    run = _get_owned_run(db, run_id, user_id)
    if run is None:
        raise HTTPException(status_code=404, detail='Reconciliation run not found.')

    transactions = db.query(BankTransaction).filter(BankTransaction.run_id == run_id).order_by(BankTransaction.transaction_date.desc()).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Date", "Description", "Amount", "Direction", "Status",
        "Matched Journal Entry", "Confidence", "Reasoning"
    ])
    for t in transactions:
        writer.writerow([
            t.transaction_date.isoformat() if t.transaction_date else '',
            t.description,
            f'{t.amount:,.2f}',
            t.direction.value,
            t.status.value,
            str(t.matched_journal_entry_id) if t.matched_journal_entry_id else '',
            f'{t.match_confidence:.2f}' if t.match_confidence is not None else '',
            t.match_reasoning or '',
        ])
    return Response(content=buf.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="reconciliation_run_{run_id}.csv"'})

@router.get('/runs/{run_id}', response_model=ReconciliationSummaryOut)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db), user_id: uuid.UUID | None = Depends(get_current_user_id)) -> ReconciliationSummaryOut:
    run = _get_owned_run(db, run_id, user_id)
    if run is None:
        raise HTTPException(status_code=404, detail='Reconciliation run not found.')
    return _build_report(db, run)

def _build_report(db: Session, run: ReconciliationRun) -> ReconciliationSummaryOut:
    txns = db.query(BankTransaction).filter(BankTransaction.run_id == run.id).order_by(BankTransaction.transaction_date.desc()).all()
    matched = [t for t in txns if t.status == BankTransactionStatus.MATCHED]
    unmatched = [t for t in txns if t.status == BankTransactionStatus.UNMATCHED]
    ignored = [t for t in txns if t.status == BankTransactionStatus.IGNORED]

    matched_je_ids = {t.matched_journal_entry_id for t in matched if t.matched_journal_entry_id}
    posted = db.query(JournalEntry, Invoice).outerjoin(Invoice, JournalEntry.invoice_id == Invoice.id).filter(JournalEntry.status == JournalEntryStatus.POSTED).all()
    unmatched_journal = [
        UnmatchedJournalEntryOut(
            journal_entry_id=je.id,
            entry_date=je.entry_date,
            vendor_name=(inv.vendor_name if inv and inv.vendor_name else je.description) or '-',
            amount=je.total_credit,
        )
        for je, inv in posted if je.id not in matched_je_ids
    ]

    return ReconciliationSummaryOut(
        id=run.id,
        filename=run.filename,
        created_at=run.created_at,
        bank_transaction_count=run.bank_transaction_count,
        matched_count=run.matched_count,
        unmatched_bank_count=run.unmatched_bank_count,
        unmatched_journal_count=run.unmatched_journal_count,
        total_matched_amount=run.total_matched_amount,
        summary=run.summary,
        matched=[BankTransactionOut.model_validate(t) for t in matched],
        unmatched_bank=[BankTransactionOut.model_validate(t) for t in unmatched],
        ignored=[BankTransactionOut.model_validate(t) for t in ignored],
        unmatched_journal=unmatched_journal,
    )