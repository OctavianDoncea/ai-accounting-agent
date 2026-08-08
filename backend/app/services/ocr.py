"""OCR pipeline: turn an uploaded invoice file (PDF or image) into raw text."""

import io
import logging
import os
import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps
from pdf2image import convert_from_path
from pypdf import PdfReader

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.tiff', '.tif', '.bmp', '.heic', '.heif'}
PDF_EXTENSIONS = {'.pdf'}

MIN_EMBEDDED_TEXT_CHARS = 100
MAX_IMAGE_DIMENSION = 3500 # Tesseract can't handle well and fast images larger than this
TESSERACT_LANG = os.environ.get('TESSERACT_LANG', 'eng')

class OCRError(Exception):
    """Raised when a file cannot be processed into text."""


def extract_text(file_path: str) -> tuple[str, str]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext in PDF_EXTENSIONS:
        return _extract_text_from_pdf(file_path)
    if ext in IMAGE_EXTENSIONS:
        if ext in ('.heic', '.heif') and not HEIC_SUPPORTED:
            raise OCRError("HEIC/HEIF images require the pillow-heif package, which isn't installed. Convert the photo to JPG/PNG first.")
        
        return _extract_from_image(file_path), 'image_ocr'

    raise OCRError(f'Unsupported file type: {ext or "(none)"}')

def _extract_text_from_pdf(file_path: str) -> tuple[str, str]:
    # Embedded text layer first
    try:
        reader = PdfReader(file_path)
        text_parts = [page.extract_text() or '' for page in reader.pages]
        embedded = '\n'.join(text_parts).strip()

        if len(embedded) >= MIN_EMBEDDED_TEXT_CHARS:
            log.info(f'Extracted {len(embedded)} chars from PDF text layer')
            return embedded, 'pdf_text_layer'
    except Exception as e:
        log.warning(f'Failed reading PDF text layer, falling back to OCR: {e}')

    # Fall back to rasterize + preprocess + OCR (used for scanned/photographed PDFs)
    try:
        images = convert_from_path(file_path, dpi=300)
    except Exception as e:
        raise OCRError(f'Could not rasterize PDF for OCR: {e}') from e

    text_parts = []
    for img in images:
        cleaned, _ = _preprocess_for_ocr(img)
        text_parts.append(pytesseract.image_to_string(cleaned, lang=TESSERACT_LANG))
    
    text = '\n'.join(text_parts).strip()
    log.info(f"OCR'd {len(images)} page(s) from scanned PDF: {len(text)} chars")
    if not text:
        raise OCRError('OCR produced no text from the PDF')
    
    return text, 'pdf_ocr'

def _extract_from_image(file_path: str) -> str:
    try:
        with Image.open(file_path) as img:
            img = ImageOps.exif_transpose(img)
            cleaned, angle = _preprocess_for_ocr(img)
            text = pytesseract.image_to_string(cleaned, lang=TESSERACT_LANG).strip()
    except OCRError:
        raise
    except Exception as e:
        raise OCRError(f'Could not OCR image: {e}') from e

    if not text:
        raise OCRError('OCR produced no text from the image')
    log.info(f"OCR'd image (deskew {angle}): {len(text)} chars")

    return text

def _preprocess_for_ocr(pil_img: Image.Image) -> tuple[Image.Image, float]:
    """Deskew, denoise, and adaptive-threshold an image before OCR."""
    img = pil_img.convert('RGB')

    # Downscaleing oversized phone photos
    w, h = img.size
    if max(w, h) > MAX_IMAGE_DIMENSION:
        scale = MAX_IMAGE_DIMENSION / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    grey = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    grey = cv2.fastNlMeansDenoising(grey, h=10) # denoise
    angle = 0.0 # deskew, even a slight tilt hurts Tesseract's performance

    try:
        threshold = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(threshold > 0))

        if coords.size() > 0:
            raw_angle = cv2.minAreaRect(coords)[-1]
            angle = -(90 + raw_angle) if raw_angle < -45 else -raw_angle
            if abs(angle) > 0.1:
                (height, width) = grey.shape
                center = (width // 2, height // 2)
                matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
                grey = cv2.warpAffine(grey, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception as e:
        log.warning(f'Deskew step failed, continuing with un-rotated image: {e}')

    # Adaptive threshold: normalizing uneven lighting
    grey = cv2.adaptiveThreshold(grey, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)

    return Image.fromarray(grey), angle

def extract_text_from_bytes(data: bytes, filename: str) -> tuple[str, str]:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            cleaned, _ = _preprocess_for_ocr(img)

            return pytesseract.image_to_string(cleaned, lang=TESSERACT_LANG).strip(), 'image_ocr'
    raise OCRError('extract_text_from_bytes only supports images; use extract_text for PDFs')