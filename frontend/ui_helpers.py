INVOICE_STATUS_BADGE = {
    'PENDING': 'Pending',
    'EXTRACTED': 'Extracted',
    'CLASSIFIED': 'Classified',
    'POSTED': 'Posted',
    'DUPLICATE': 'Duplicate',
    'NEEDS_REVIEW': 'Needs review',
    'FAILED': 'Failed',
}

JE_STATUS_BADGE = {
    'POSTED': 'Posted',
    'DRAFT': 'Draft',
    'REVERSED': 'Reversed',
}

BANK_TXN_STATUS_BADGE = {
    'MATCHED': 'Matched',
    'UNMATCHED': 'Unmatched',
    'IGNORED': 'Ignored',
}

def format_money(value, currency: str = '') -> str:
    if value is None or value == '':
        return '-'
    try:
        n = float(value)
    except (ValueError, TypeError):
        return str(value)
    formatted = f"{n:,.2f}"
    return f'{currency} {formatted}' if currency else formatted

def format_date(value) -> str:
    if not value:
        return '-'
    s = str(value)
    return s[:10] if len(s) >= 10 else s