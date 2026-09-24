"""Learn and recall which GL account a vendor's line items post to."""

from collections import Counter
from sqlalchemy.orm import Session
from app.models.chart_of_accounts import ChartOfAccount
from app.models.invoice import Invoice
from app.models.journal_entry import JournalEntry, JournalEntryLines, JournalEntryType
from app.models.vendor_memory import VendorAccountMemory, normalize_vendor
from app.services.journal_entry_builder import FALLBACK_TAX_CODE as TAX_ACCOUNT_CODE

def record_post(db: Session, invoice: Invoice, entry: JournalEntry) -> None:
    if entry.entry_type != JournalEntryType.BILL:
        return
    
    vendor_key = normalize_vendor(invoice.vendor_name)

    if not vendor_key:
        return

    account_lookup = {a.id: a for a in db.query(ChartOfAccount).all()}
    tax_line_Account_ids = {
        line.account_id
        for line in entry.lines
        if (account_lookup.get(line.account_id) and account_lookup[line.account_id].account_code == TAX_ACCOUNT_CODE)
    }
    codes = []

    for line in entry.lines:
        if line.debit_amount and line.debit_amount > 0 and line.account_id not in tax_line_Account_ids:
            acct = account_lookup.get(line.account_id)
            if acct is not None:
                codes.append(acct.account_code)

    for code in set(codes):
        row = db.query(VendorAccountMemory).filter(
            VendorAccountMemory.user_id == invoice.user_id,
            VendorAccountMemory.vendor_key == vendor_key,
            VendorAccountMemory.account_code == code
        ).first()

        if row is None:
            row = VendorAccountMemory(
                user_id = invoice.user_id,
                vendor_key = vendor_key,
                vendor_display = invoice.vendor_name or vendor_key,
                account_code = code,
                times_seen = 1
            )
            db.add(row)
        else:
            row.times_seen += 1
            row.vendor_display = invoice.vendor_name or vendor_key

    db.commit()

def preffered_account(db: Session, user_id, vendor_name: str | None) -> str | None:
    vendor_key = normalize_vendor(vendor_name)

    if not vendor_key:
        return None
    
    rows = db.query(VendorAccountMemory).filter(
        VendorAccountMemory.user_id == user_id,
        VendorAccountMemory.vendor_key == vendor_key
    ).order_by(VendorAccountMemory.times_seen.desc(), VendorAccountMemory.updated_at.desc()).all()

    if not rows:
        return None

    return rows[0].account_code

def vendor_stats(db: Session, user_id) -> list[dict]:
    rows = db.query(VendorAccountMemory).filter(VendorAccountMemory.user_id == user_id).order_by(VendorAccountMemory.times_seen.desc()).all()
    by_vendor: dict[str, dict] = {}

    for r in rows:
        entry = by_vendor.setdefault(r.vendor_key, {'vendor': r.vendor_display, 'total_posts': 0, 'accounts': []})
        entry['total_posts'] += r.times_seen
        entry['accounts'].append({'account_code': r.account_code, 'times_seen': r.times_seen})

    return list(by_vendor.values())