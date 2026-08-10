import uuid
from datetime import timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.invoice import Invoice, InvoiceStatus

DATE_TOLERANCE_DAYS = 3

def find_duplicate(db: Session, invoice: Invoice) -> Invoice | None:
    base_query = db.query(Invoice).filter(
        Invoice.id != invoice.id,
        Invoice.status != InvoiceStatus.DUPLICATE,
        Invoice.status != InvoiceStatus.FAILED,
        Invoice.user_id == invoice.user_id
    )

    if invoice.vendor_name and invoice.invoice_number:
        match = (
            base_query.filter(
                func.lower(Invoice.vendor_name) == invoice.vendor_name.lower(),
                Invoice.invoice_number == invoice.invoice_number
            )
            .order_by(Invoice.upload_date.asc())
            .first()
        )
        if match:
            return match

    if invoice.vendor_name and invoice.total is not None:
        candidates = base_query.filter(
            func.lower(Invoice.vendor_name) == invoice.vendor_name.lower(),
            Invoice.total == invoice.total
        ).all()
        for cand in candidates:
            if _dates_close(invoice, cand):
                return cand

    return None

def _dates_close(a: Invoice, b: Invoice) -> bool:
    if a.invoice_date is None or b.invoice_date is None:
        return True
    return abs((a.invoice_date - b.invoice_date).days) <= DATE_TOLERANCE_DAYS