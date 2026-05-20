import io
import logging
import os
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
from pypdf import PdfReader

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.tif', '.webp'}
PDF_EXTENSIONS = {'.pdf'}

MIN_EMBEDDED_TEXT_CHARS = 100

class OCRError(Exception):
    """Raised when a file cannot be processed into text."""


def extract_text(file_path: str) -> tuple[str, str]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext in PDF_EXTENSIONS:
        return _extract_from_pdf(file_path)
    if ext in IMAGE_EXTENSIONS:
        return _extract_from_image(file_path), 'image_ocr'

    raise OCRError(f'Unsupported file type: {ext}')

def _extract_from_pdf(file_path: str) -> tuple[str, str]:
    # Try the embedded text layer first
    try:
        reader = PdfReader(file_path)
        text_parts = [page.extract_text() or '' for page in reader.pages]
        embedded = '\n'.join(text_parts).strip()
        if len(embedded) >= MIN_EMBEDDED_TEXT_CHARS:
            log.info(f'Extracted {len(embedded)} characters from PDF text layer')
            return embedded, 'pdf_text_layer'
    except Exception as e:
        log.warning(f'Failed reading PDF text layer, falling back to OCR: {e}')

    # Fall back to OCR
    try:
        images = convert_from_path(file_path, dpi=300)
    except Exception as e:
        raise OCRError(f'Could not rasterize PDF foe OCR: {e}') from e

    text_parts = [pytesseract.image_to_string(img) for img in images]
    text = '/n'.join(text_parts).strip()
    log.info(f"OCR'd {len(images)} page(s) from scanned PDF -> {len(text)} chars")
    if not text:
        raise OCRError('No text found after OCR')
    return text, 'pdf_ocr'

def _extract_from_image(file_path: str) -> str:
    try:
        with Image.open(file_path) as img:
            text = pytesseract.image_to_string(img).strip()
    except Exception as e:
        raise OCRError(f'Could not process image: {e}') from e
    
    if not text:
        raise OCRError('OCR produced no text from the image')
    log.info(f"OCR'd image -> {len(text)} chars")
    return text

def extract_text_from_bytes(data: bytes, filename: str) -> tuple[str, str]:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        with Image.open(io.BytesIO(data)) as img:
            return pytesseract.image_to_string(img).strip(), 'image_ocr'
    raise OCRError('extract_text_from_bytes only supports images; use extract_text for PDFs')