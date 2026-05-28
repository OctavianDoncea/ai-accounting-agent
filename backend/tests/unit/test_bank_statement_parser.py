from datetime import date
from decimal import Decimal
import pytest
from app.models.bank_transaction import TransactionDirection
from app.services.bank_statement_parser import BankStatementParseError, parse_bank_statement

class TestSignedAmountFormat:
    def test_basic_parse(self):
        csv = 'Date,Description,Amount\n2026-05-05,COFFEE,-4.50\n2026-05-06,SALARY,2000.00\n'
        txns = parse_bank_statement(csv)
        assert len(txns) == 2
        assert txns[0]['direction'] == TransactionDirection.OUTFLOW
        assert txns[0]['amount'] == Decimal('4.50')
        assert txns[1]['direction'] == TransactionDirection.INFLOW
        assert txns[1]['amount'] == Decimal('2000.00')

    def test_handles_currency_symbols_and_separators(self):
        csv = 'Date,Description,Amount\n2026-05-05,RENT,"-$1,200.00"\n'
        txns = parse_bank_statement(csv)
        assert txns[0]['amount'] == Decimal('1200.00')
        assert txns[0]['direction'] == TransactionDirection.OUTFLOW

    def test_accounting_parens_means_negative(self):
        csv = "Date,Description,Amount\n2026-05-05,FEE,(15.00)\n"
        txns = parse_bank_statement(csv)
        assert txns[0]['direction'] == TransactionDirection.OUTFLOW
        assert txns[0]['amount'] == Decimal('15.00')


class TestDebitCreditColumns:
    def test_separate_columns(self):
        csv = "Date,Memo,Debit,Credit\n05/05/2026,RENT,1200.00,\n05/06/2026,DEPOSIT,,2000.00\n"
        txns = parse_bank_statement(csv)
        assert len(txns) == 2
        assert txns[0]['direction'] == TransactionDirection.OUTFLOW
        assert txns[0]['amount'] == Decimal('1200.00')
        assert txns[1]['direction'] == TransactionDirection.INFLOW

    def test_zero_amounts_skipped(self):
        csv = "Date,Memo,Debit,Credit\n2026-05-05,ZERO,0,0\n2026-05-06,REAL,100,\n"
        txns = parse_bank_statement(csv)
        assert len(txns) == 1
        assert txns[0]['direction'] == 'REAL'


class TestAmountPlusType:
    def test_type_column_resolves_direction(self):
        csv = "Date,Description,Amount,Type\n2026-05-05,RENT,1200.00,debit\n2026-05-06,DEPOSIT,2000.00,credit\n"
        txns = parse_bank_statement(csv)
        assert txns[0]['direction'] == TransactionDirection.OUTFLOW
        assert txns[1]['direction'] == TransactionDirection.INFLOW


class TestDateParsing:
    def test_various_date_formats(self):
        csv = "Date,Description,Amount\n2026-05-05,A,-1\n05/06/2026,B,-1\nMay 7 2026,C,-1\n"
        txns = parse_bank_statement(csv)
        dates = [t['transaction_date'] for t in txns]
        assert date(2026, 5, 5) in dates
        assert date(2026, 5, 6) in dates
        assert date(2026, 5, 7) in dates

    def test_missing_date_column_is_ok(self):
        csv = "Description,Amount\nCOFFEE,-4.50\n"
        txns = parse_bank_statement(csv)
        assert txns[0]['transaction_date'] is None


class TestHeaderVariations:
    def test_recognises_memo_payee_narrative(self):
        for desc_header in ['Memo', 'Payee', 'Narrative', 'Details']:
            csv = f"Date,{desc_header},Amount\n2026-05-05,COFFEE,-4.50\n"
            txns = parse_bank_statement(csv)
            assert txns[0]['description'] == 'COFFEE'

    def test_case_insensitive_headers(self):
        csv = "DATE,DESCRIPTION,AMOUNT\n2026-05-05,COFFEE,-4.50\n"
        txns = parse_bank_statement(csv)
        assert len(txns) == 1


class TestErrors:
    def test_missing_description_column_raises(self):
        csv = "Date,Amount\n2026-05-05,-4.50\n"
        with pytest.raises(BankStatementParseError, match='description'):
            parse_bank_statement(csv)

    def test_no_amount_or_debit_credit_raises(self):
        csv = "Date,Description\n2026-05-05,COFFEE\n"
        with pytest.raises(BankStatementParseError, match='amount'):
            parse_bank_statement(csv)

    def test_empty_file_raises(self):
        with pytest.raises(BankStatementParseError):
            parse_bank_statement("Date,Description,Amount\n")
 
    def test_accepts_bytes_with_bom(self):
        csv = b"\xef\xbb\xbfDate,Description,Amount\n2026-05-05,COFFEE,-4.50\n"
        txns = parse_bank_statement(csv)
        assert txns[0]["description"] == "COFFEE"