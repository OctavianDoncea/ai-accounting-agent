"""Generate realistic sample invoice PDFs for testing the extraction pipeline.
 
Run:  python samples/generate_samples.py
Output: samples/*.pdf
"""

import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

SAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))

def _draw_invoice(path: str, data: dict) -> None:
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter

    # Header
    c.setFont('Helvetica-Bold', 22)
    c.drawString(1 * inch, height - 1 * inch, data['vendor'])
    c.setFont('Helvetica', 9)
    c.drawString(1 * inch, height - 1.25 * inch, data['vendor_address'])

    c.setFont('Helvetica-Bold', 26)
    c.setFillColor(colors.HexColor('#2a6f7f'))
    c.drawRightString(width - 1 * inch, height - 1 * inch, 'INVOICE')
    c.setFillColor(colors.black)

    # Meta
    c.setFont('Helvetica', 10)
    meta_y = height - 1.7 * inch
    c.drawRightString(width - 1 * inch, meta_y, f'Invoice: {data['invoice_number']}')
    c.drawRightString(width - 1 * inch, meta_y - 0.25 * inch, f'Date: {data['invoice_date']}')
    c.drawRightString(width - 1 * inch, meta_y - 0.5 * inch, f'Due date: {data['due_date']}')

    # Bill to
    c.setFont('Helvetica-Bold', 10)
    c.drawString(1 * inch, meta_y, 'Bill to:')
    c.setFont('Helvetica', 10)
    c.drawString(1 * inch, meta_y - 0.2 * inch, data['bill_to'])

    # Table header
    table_top = height - 3 * inch
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#2a6f7f"))
    c.rect(1 * inch, table_top - 0.05 * inch, width - 2 * inch, 0.3 * inch, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.drawString(1.1 * inch, table_top + 0.05 * inch, "Description")
    c.drawString(4.6 * inch, table_top + 0.05 * inch, "Qty")
    c.drawString(5.4 * inch, table_top + 0.05 * inch, "Unit Price")
    c.drawRightString(width - 1.1 * inch, table_top + 0.05 * inch, "Amount")
    c.setFillColor(colors.black)
 
    # Rows
    c.setFont("Helvetica", 10)
    row_y = table_top - 0.35 * inch
    for item in data["line_items"]:
        c.drawString(1.1 * inch, row_y, item["description"])
        c.drawString(4.6 * inch, row_y, str(item["qty"]))
        c.drawString(5.4 * inch, row_y, f"{data['currency_symbol']}{item['unit_price']:.2f}")
        c.drawRightString(width - 1.1 * inch, row_y, f"{data['currency_symbol']}{item['amount']:.2f}")
        row_y -= 0.3 * inch
 
    # Totals
    row_y -= 0.2 * inch
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 2.2 * inch, row_y, "Subtotal:")
    c.drawRightString(width - 1.1 * inch, row_y, f"{data['currency_symbol']}{data['subtotal']:.2f}")
    row_y -= 0.25 * inch
    c.drawRightString(width - 2.2 * inch, row_y, f"Tax ({data['tax_rate']}):")
    c.drawRightString(width - 1.1 * inch, row_y, f"{data['currency_symbol']}{data['tax']:.2f}")
    row_y -= 0.25 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 2.2 * inch, row_y, "Total:")
    c.drawRightString(width - 1.1 * inch, row_y, f"{data['currency_symbol']}{data['total']:.2f}")
 
    # Footer
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.grey)
    c.drawString(1 * inch, 1 * inch, data.get("notes", "Thank you for your business!"))
 
    c.showPage()
    c.save()
 
SAMPLES = [
    {
        "filename": "invoice_cloudhost.pdf",
        "vendor": "CloudHost Solutions Inc.",
        "vendor_address": "500 Server Lane, Austin, TX 78701",
        "invoice_number": "CH-2026-00871",
        "invoice_date": "2026-04-15",
        "due_date": "2026-05-15",
        "bill_to": "Acme Startup LLC",
        "currency_symbol": "$",
        "line_items": [
            {"description": "Cloud hosting - Production tier (April)", "qty": 1, "unit_price": 249.00, "amount": 249.00},
            {"description": "Object storage - 500GB", "qty": 1, "unit_price": 45.00, "amount": 45.00},
            {"description": "Managed PostgreSQL database", "qty": 1, "unit_price": 89.00, "amount": 89.00},
        ],
        "subtotal": 383.00,
        "tax_rate": "8.25%",
        "tax": 31.60,
        "total": 414.60,
        "notes": "Auto-billed to card on file. Thank you!",
    },
    {
        "filename": "invoice_officedepot.pdf",
        "vendor": "Office Depot",
        "vendor_address": "12 Commerce Blvd, Boca Raton, FL 33496",
        "invoice_number": "OD-558213",
        "invoice_date": "2026-04-22",
        "due_date": "2026-05-22",
        "bill_to": "Acme Startup LLC",
        "currency_symbol": "$",
        "line_items": [
            {"description": "Printer paper, A4 (case of 10)", "qty": 2, "unit_price": 42.50, "amount": 85.00},
            {"description": "Ergonomic office chair", "qty": 1, "unit_price": 320.00, "amount": 320.00},
            {"description": "Wireless mouse", "qty": 3, "unit_price": 24.99, "amount": 74.97},
        ],
        "subtotal": 479.97,
        "tax_rate": "6%",
        "tax": 28.80,
        "total": 508.77,
        "notes": "Net 30. Returns accepted within 14 days.",
    },
    {
        "filename": "invoice_lawfirm.pdf",
        "vendor": "Brightman & Associates LLP",
        "vendor_address": "1 Legal Plaza, Suite 900, New York, NY 10005",
        "invoice_number": "INV-2026-0342",
        "invoice_date": "2026-05-01",
        "due_date": "2026-05-31",
        "bill_to": "Acme Startup LLC",
        "currency_symbol": "$",
        "line_items": [
            {"description": "Legal consultation - incorporation review", "qty": 4, "unit_price": 350.00, "amount": 1400.00},
            {"description": "Contract drafting - vendor agreement", "qty": 2, "unit_price": 350.00, "amount": 700.00},
        ],
        "subtotal": 2100.00,
        "tax_rate": "0%",
        "tax": 0.00,
        "total": 2100.00,
        "notes": "Payment due within 30 days of invoice date.",
    },
    {
        'filename': 'invoice_marketingsaas.pdf',
        'vendor': 'PixelPulse Analytics',
        'vendor_address': '88 Market Street, San Francisco, CA 94103',
        'invoice_number': 'PP-INV-9921',
        'invoice_date': '2026-04-28',
        'due_date': '2026-05-28',
        'bill_to': 'Acme Startup LLC',
        'currency_symbol': '$',
        'line_items': [
            {'description': 'MArketing analytics platform - Pro plan (April)', 'qty': 1, 'unit_price': 199.00, 'amount': 199.00},
            {'description': 'Additional team seats (3)', 'qty': 3, 'unit_price': 29.00, 'amount': 87.00},
        ],
        'subtotal': 286.00,
        'tax_rate': '8.5%',
        'tax': 24.31,
        'total': 310.31,
        'notes': 'Subscription auto-renews monthly. Cancel anytime.'
    },
    {
        'filename': 'invoice_accountant.pdf',
        'vendor': 'Reeves Bookkeeping Co.',
        'vendor_address': '240 PArk Avenue, Boston, MA 02116',
        'invoice_number': 'RB-1247',
        'invoice_date': '2026-05-03',
        'due_date': '2026-06-02',
        'bill_to': 'Acme Startup LLC',
        'currency_symbol': '$',
        'line_items': [
            {"description": "Monthly bookkeeping - April", "qty": 1, "unit_price": 450.00, "amount": 450.00},
            {"description": "Sales tax filing assistance", "qty": 1, "unit_price": 150.00, "amount": 150.00}
        ],
        'subtotal': 600.00,
        'tax_rate': '0%',
        'tax': 0.00,
        'total': 600.00,
        'notes': 'Thank you for your continued business.'
    }
]

def main() -> None:
    for sample in SAMPLES:
        path = os.path.join(SAMPLES_DIR, sample["filename"])
        _draw_invoice(path, sample)
        print(f"Wrote {path}")
 
 
if __name__ == "__main__":
    main()
 