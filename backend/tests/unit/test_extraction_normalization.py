from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from app.agents.extraction_agent import ExtractionAgent, _to_date, _to_decimal, _clean_str

class TestToDecimal:
    def test_plain_number(self):
        assert _to_decimal('123.45') == Decimal('123.45')

    def test_int_and_float(self):
        assert _to_decimal(100) == Decimal('100')
        assert _to_decimal(99.5) == Decimal('99.5')

    def test_strips_currency_symbols(self):
        assert _to_decimal('$123.45') == Decimal('123.45')
        assert _to_decimal('€123.45') == Decimal('123.45')
        assert _to_decimal('£123.45') == Decimal('123.45')

    def test_strips_thousands_separators(self):
        assert _to_decimal('1,234.56') == Decimal('1234.56')
        assert _to_decimal('$1,234.56') == Decimal('1234.56')

    def test_none_and_empty(self):
        assert _to_decimal(None) is None
        assert _to_decimal('') is None
        assert _to_decimal('    ') is None

    def test_invalid_returns_none(self):
        assert _to_decimal('abc') is None
        assert _to_decimal('abc12345abc') is None


class TestToDate:
    def test_iso_format(self):
        assert _to_date('2026-04-15') == date(2026, 4, 15)

    def test_natural_language(self):
        assert _to_date('April 15, 2026') == date(2026, 4, 15)
        assert _to_date('15th April 2026') == date(2026, 4, 15)

    def test_us_format(self):
        assert _to_date('4/15/2026') == date(2026, 4, 15)

    def test_none_and_empty(self):
        assert _to_date(None) is None
        assert _to_date('') is None

    def test_invalid_returns_none(self):
        assert _to_date('abc') is None


class TestCleanStr:
    def test_strips_whitespace(self):
        assert _clean_str('  Hello, world!  ') == 'Hello, world!'

    def test_empty_becomes_none(self):
        assert _clean_str('') is None
        assert _clean_str('    ') is None
        assert _clean_str(None) is None


class TestNormalize:
    """End-to-end normalization of a messy LLM response."""

    def _agent(self):
        client = MagicMock()
        return ExtractionAgent(client=client)

    def test_handles_messy_response(self):
        raw = {
            'vendor_name': '  CloudHost Solutions Inc.  ',
            'invoice_number': 'CH-2026-00871',
            'invoice_date': 'April 15, 2026',
            'due_date': '2026-05-15',
            'currency': 'usd',
            'subtotal': '$1,234.56',
            'tax': 100.0,
            'total': '1,334.56',
            'line_items': [
                {'description': 'Item A', 'quantity': 2, 'unit_price': '$50', 'amount': 100},
                {'description': '', 'quantity': 1, 'unit_price': 0, 'amount': 0},
            ],
            'confidence': 0.93,
            'reasoning': 'Looks good.'
        }
        result = self._agent()._normalize(raw)

        assert result.vendor_name == 'CloudHost Solutions Inc.'
        assert result.invoice_date == date(2026, 4, 15)
        assert result.currency == 'USD'
        assert result.subtotal == Decimal('1234.56')
        assert result.tax == Decimal('100.00')
        assert result.total == Decimal('1334.56')
        assert result.confidence == 0.93
        assert len(result.line_items) == 1
        assert result.line_items[0].description == 'Item A'

    def test_clamps_confidence(self):
        raw = {'confidence': 1.5, 'line_items': []}
        assert self._agent()._normalize(raw).confidence == 1.0

        raw = {'confidence': -0.2, 'line_items': []}
        assert self._agent()._normalize(raw).confidence == 0.0

    def test_invalid_confidence_defaults_to_half(self):
        raw = {'confidence': 'high', 'line_items': []}
        assert self._agent()._normalize(raw).confidence == 0.5

    def test_missing_fields_become_none(self):
        result = self._agent()._normalize({'line_items': []})
        assert result.vendor_name is None
        assert result.total is None
        assert result.invoice_date is None
        assert result.currency == 'USD'

    def test_truncate_three_letter_currency(self):
        result = self._agent()._normalize({'currency': 'US dollars', 'line_items': []})
        assert result.currency == 'UNI'

    def test_non_dict_line_items_are_skipped(self):
        raw = {'line_items': ['not a dict', {'description': 'ok', 'amount': 5}]}
        result = self._agent()._normalize(raw)
        assert len(result.line_items) == 1