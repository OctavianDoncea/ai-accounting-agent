import uuid
import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.chart_of_accounts import ChartOfAccount
from app.models.journal_entry import JournalEntry
from app.schemas.journal_entry import JournalEntryLineOut, JournalEntryOut

router = APIRouter(prefix='/journal-entries', tags=['journal-entries'])

def _serialize(db: Session, entry: JournalEntry) -> JournalEntryOut:
    account_lookup = {a.id: a for a in db.query(ChartOfAccount).all()}
    lines = []
    for line in entry.lines:
        acct = account_lookup.get(line.account_id)
        lines.append(JournalEntryLineOut(
            id=line.id,
            account_id=line.account_id,
            account_code=acct.account_code if acct else None,
            account_name=acct.account_name if acct else None,
            debit_amount=line.debit_amount,
            credit_amount=line.credit_amount,
            description=line.description,
            confidence_score=line.confidence_score,
        ))

    return JournalEntryOut(
        id=entry.id,
        invoice_id=entry.invoice_id,
        entry_date=entry.entry_date,
        description=entry.description,
        status=entry.status,
        total_debit=entry.total_debit,
        total_credit=entry.total_credit,
        created_at=entry.created_at,
        lines=lines,
    )

@router.get('', response_model=list[JournalEntryOut])
def list_journal_entries(limit: int = 100, db: Session = Depends(get_db)) -> list[JournalEntryOut]:
    entries = db.query(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(limit).all()
    return [_serialize(db, e) for e in entries]

@router.get('/export', response_class=Response)
def export_journal_entries(db: Session = Depends(get_db)) -> Response:
    """Export all journal entries as CSV (one row per debit/credit line)."""
    entries = db.query(JournalEntry).order_by(JournalEntry.entry_date.desc()).all()
    account_lookup = {a.id: a for a in db.query(ChartOfAccount).all()}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Entry ID", "Entry Date", "Description", "Status",
        "Account Code", "Account Name", "Debit", "Credit", "Memo", "Confidence",
    ])
    for je in entries:
        for line in je.lines:
            acct = account_lookup.get(line.account_id)
            writer.writerow([
                str(je.id), je.entry_date.isoformat() if je.entry_date else '',
                je.description, je.status.value,
                acct.account_code if acct else '',
                acct.account_name if acct else '',
                f'{line.debit_amount:,.2f}' if line.debit_amount else '',
                f'{line.credit_amount:,.2f}' if line.credit_amount else '',
                line.description or '',
                f'{line.confidence_score:.2f}' if line.confidence_score is not None else '',
            ])
    return Response(content=buf.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="journal_entries.csv"'})

@router.get('/{entry_id}', response_model=JournalEntryOut)
def get_journal_entry(entry_id: uuid.UUID, db: Session = Depends(get_db)) -> JournalEntryOut:
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f'Journal entry not found')
    return _serialize(db, entry)