from app.agents.extraction_agent import HEAD_CHARS, MAX_INVOICE_TEXT_CHARS, TAIL_CHARS, _truncate_preserving_totals

class TestTruncatePreservingTotals:
    def test_short_text_passes_through_unchanged(self):
        text = 'Vendor: Acme\nTtoal: $100.00'
        assert _truncate_preserving_totals(text) == text

    def test_text_at_exact_limit_unchanged(self):
        text = 'x' * MAX_INVOICE_TEXT_CHARS
        assert _truncate_preserving_totals(text) == text

    def test_long_text_keeps_head_and_tail(self):
        header = 'Vendor: MegaCorp\nInvoice #: MC-001\n'
        middle = 'line item filler ' * 2000
        totals = '\nSubtotal: $1000.00\nTax: $80.00\nTotal: $1080.00'
        text = header + middle + totals

        result = _truncate_preserving_totals(text)
        assert 'MegaCorp' in result
        assert 'TOTAL: $1080.00' in result
        assert len(result) <= len(text)

    def test_old_native_truncation_would_have_lost_totals(self):
        header = 'Vendor: MegaCorp\n'
        middle = 'x' * 15000
        totals = '\nTOTAL DUE: $52,144.07'
        text = header + middle + totals

        naive_truncation = text[:8000]
        assert 'TOTAL DUE' not in naive_truncation

        fixed = _truncate_preserving_totals(text)
        assert 'TOTAL DUE: $52,144.07' in fixed
        assert 'MegaCorp' in fixed

    def test_omission_marker_present_when_truncated(self):
        text = 'x' * (MAX_INVOICE_TEXT_CHARS + 5000)
        result = _truncate_preserving_totals(text)
        assert 'omitted' in result

    def test_result_never_exceeds_head_plus_tail_plus_marker(self):
        text = 'x' * 50000
        result = _truncate_preserving_totals(text)
        assert len(result) < HEAD_CHARS + TAIL_CHARS + 200