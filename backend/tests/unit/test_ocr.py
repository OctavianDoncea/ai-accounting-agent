import os
import pytest
from app.services.ocr import extract_text, OCRError

SAMPLES = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'samples')

@pytest.mark.parametrize('filename,expected_keywords', [
    ('invoice_cloudhost.pdf', ['CloudHost', '414.60', 'CH-2026-00871']),
    ('invoice_officedepot.pdf', ['Office Depot', '508.77']),
    ('invoice_lawfirm.pdf', ['Brightman', '2100.00'])
])
def test_extract_text_layer_from_digital_pdf(filename, expected_keywords):
    path = os.path.join(SAMPLES, filename)
    if not os.path.exists(path):
        pytest.skip(f'Sample missing: {path}')
    text, method = extract_text(path)
    assert method == 'pdf_text_layer'
    for keyword in expected_keywords:
        assert keyword in text, f'expected {keyword!r} in extracted text'

def test_unsupported_extension_raises():
    with pytest.raises(OCRError):
        extract_text('/tmp/file.docx')