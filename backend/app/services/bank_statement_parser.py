"""Parse a bank-statement CSV into normalized bank transactions"""

import csv
import io
import logging
from datetime import date
from decimal import Decimal, InvalidOperation, Overflow
from re import L
from dateutil import parser as date_parser
from app.models.bank_transaction import TransactionDirection

log = logging.getLogger(__name__)

DATE_HEADERS = {'date', 'transaction date', 'txn date', 'posted date', 'posting date', 'value date'}
DESC_HEADERS = {'description', 'memo', 'narrative', 'details', 'payee', 'name', 'reference', 'transaction'}
AMOUNT_HEADERS = {'amount', 'value', 'transacion amount'}
DEBIT_HEADERS = {'debit', 'withdrawal', 'withdrawals', 'debit amount', 'money out', 'paid out', 'outflow'}
CREDIT_HEADERS = {'credit', 'deposit', 'deposits', 'credit amount', 'money in', 'paid in', 'inflow'}
TYPE_HEADERS = {'type', 'transaction type', 'dr/cr', 'debit/credit', 'direction'}

class BankStatementParseError(Exception):
    pass


def _find(headers: dict[str, str], candidates: set[str]) -> str | None:
    for actual_lower, actual in headers.items():
        if actual_lower in candidates:
            return actual
    
    return None

def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    negative = cleaned.startswith('(') and cleaned.endswith(')')

    for ch in ["$", "€", "£", "¥", " ", ",", "(", ")"]:
        cleaned = cleaned.replace(ch, '')
    if not cleaned:
        return None
        
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None

    return -amount if negative else amount

def _to_date(value: str | None) -> date | None:
    if not value or not str(value).strip():
        return None
    
    try:
        return date_parser.parse(str(value), dayfirst=False, fuzzy=True).date()
    except (ValueError, Overflow):
        return None

def parse_bank_statement(content: bytes | str) -> list[dict]:
    text = content.decode('utf-8-sig') if isinstance(content, bytes) else content
    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        raise BankStatementParseError('CSV has no header row.')

    headers = {h.strip().lower(): h for h in reader.fieldnames if h}

    date_col = _find(headers, DATE_HEADERS)
    desc_col = _find(headers, DESC_HEADERS)
    amount_col = _find(headers, AMOUNT_HEADERS)
    debit_col = _find(headers, DEBIT_HEADERS)
    credit_col = _find(headers, CREDIT_HEADERS)
    type_col = _find(headers, TYPE_HEADERS)

    if desc_col is None:
        raise BankStatementParseError(f'Could not find a description column. Headers seen: {list(headers.values())}')
    
    if amount_col is None and debit_col is None and credit_col is None:
        raise BankStatementParseError('Could not find an amount, debit, or credit column.')
    
    transactions: list[dict] = []
    for row in reader:
        description = (row.get(desc_col) or '').strip()
        if not description:
            continue

        amount, direction = _resolve_amount(row, amount_col, debit_col, credit_col, type_col)
        if amount is None:
            continue

        transactions.append({
            'transaction_date': _to_date(row.get(date_col)) if date_col else None,
            'description': description[:500],
            'amount': abs(amount),
            'direction': direction,
            'raw_row': {k: v for k, v in row.items() if k}
        })

    if not transactions:
        raise BankStatementParseError('No valid transactions found in the statement.')
    
    return transactions

def _resolve_amount(row, amount_col ,debit_col, credit_col, type_col):
    # Case 1: separate debit / credit columns
    if debit_col or credit_col:
        debit = _to_decimal(row.get(debit_col)) if debit_col else None
        credit = _to_decimal(row.get(credit_col)) if credit_col else None

        if debit and debit != 0:
            return debit, TransactionDirection.OUTFLOW
        if credit and credit != 0:
            return credit, TransactionDirection.INFLOW
        
        return None, None

    # Case 2: single amount column
    amount = _to_decimal(row.get(amount_col))
    if amount is None or amount == 0:
        return None, None

    if type_col:
        type_val = (row.get(type_col) or '').strip().lower()
        if type_val in {'debit', 'dr', 'withdrawal', 'payment', 'out'}:
            return amount, TransactionDirection.OUTFLOW
        if type_val in {'credit', 'cr', 'deposit', 'in'}:
            return amount, TransactionDirection.INFLOW

    if amount < 0:
        return amount, TransactionDirection.OUTFLOW
    return amount, TransactionDirection.INFLOW