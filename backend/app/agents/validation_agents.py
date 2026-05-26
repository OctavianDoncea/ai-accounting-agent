from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.chart_of_accounts import ChartOfAccount
from app.models.journal_entry import JournalEntry, JournalEntryLines
from app.schemas.journal_entry import ValidationResult

BALANCE_TOLERANCE = Decimal('0.01')

def validate_entry(db: Session, entry: JournalEntry) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    valid_account_ids = {a.id for a in db.query(ChartOfAccount).filter(ChartOfAccount.is_active.is_(True)).all()}

    lines = (db.query(JournalEntryLines).filter(JournalEntryLines.journal_entry_id == entry.id).all())

    total_debit = Decimal('0')
    total_credit = Decimal('0')
    debit_lines = 0
    credit_lines = 0

    for i, line in enumerate(lines):
        debit = line.debit_amount or Decimal('0')
        credit = line.credit_amount or Decimal('0')

        if debit < 0 or credit < 0:
            errors.append(f"Line {i}: negative amount not allowed.")
        if debit > 0 and credit > 0:
            errors.append(f"Line {i}: a line cannot be both a debit and a credit.")
        if debit == 0 and credit == 0:
            errors.append(f"Line {i}: line has neither a debit nor a credit amount.")
        if line.account_id not in valid_account_ids:
            errors.append(f'Line {i}: account id {line.account_id} is not a valid active account.')

        if debit > 0:
            debit_lines += 1
        if credit > 0:
            credit_lines += 1
        total_debit += debit
        total_credit += credit

    if debit_lines == 0:
        errors.append('Entry has no debit lines.')
    if credit_lines == 0:
        errors.append('Entry has no credit lines.')

    imbalance = abs(total_debit - total_credit)
    if imbalance > BALANCE_TOLERANCE:
        errors.append(
            f'Entry does not balance: debits {total_debit} vs credits {total_credit}'
            f'(difference {imbalance})'
        )
    elif imbalance > 0:
        warnings.append(f'Sub-cent rounding difference of {imbalance} (with tolerance).')

    return ValidationResult(is_valid=not errors, errors=errors, warnings=warnings)