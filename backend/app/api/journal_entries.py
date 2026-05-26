import uuid
from fastapi import APIRouter, Depends, HTTPException
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
        invoice_id=entry.invoice.id,
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

@router.get('/{entry_id}', response_model=JournalEntryOut)
def get_journal_entry(entry_id: uuid.UUID, db: Session = Depends(get_db)) -> JournalEntryOut:
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f'Journal entry not found')
    return _serialize(db, entry)