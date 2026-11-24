import io
import os
import shutil
import tempfile
import numpy as np
import pytest
from PIL import Image, ImageEnhance
from app.services.ocr import HEIC_SUPPORTED, MAX_IMAGE_DIMENSION, OCRError, _preprocess_for_ocr, extract_text

SAMPLES = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'samples')

def _prepend_dir(directory: str) -> None:
    os.environ['PATH'] = directory + os.pathsep + os.environ.get('PATH', '')

def _ensure_ocr_tools() -> None:
    if shutil.which('pdftoppm') is None and shutil.which('pdfinfo') is None:
        local = os.environ.get('LOCALAPPDATA', '')
        winget = os.path.join(local, 'Microsoft', 'WinGet', 'Packages')
        if os.path.isdir(winget):
            for dirpath, _dirnames, filenames in os.walk(winget):
                if 'pdftoppm.exe' in filenames:
                    _prepend_dir(dirpath)
                    break
    if shutil.which('tesseract') is None:
        for directory in (
            os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'Tesseract-OCR'),
            os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Tesseract-OCR'),
        ):
            if os.path.isfile(os.path.join(directory, 'tesseract.exe')):
                _prepend_dir(directory)
                break

def _make_messy_photo() -> str:
    from pdf2image import convert_from_path

    _ensure_ocr_tools()
    if shutil.which('pdftoppm') is None and shutil.which('pdfinfo') is None:
        pytest.skip('poppler is not installed')

    path = os.path.join(SAMPLES, 'invoice_officedepot.pdf')
    if not os.path.exists(path):
        pytest.skip('Sample invoice not found')

    images = convert_from_path(path, dpi=200)
    img = images[0].convert('RGB')
    img = ImageEnhance.Contrast(img).enhance(0.6)
    img = ImageEnhance.Brightness(img).enhance(0.85)

    arr = np.array(img).astype(np.int16)
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 12, arr.shape).astype(np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)

    out_path = os.path.join(tempfile.gettempdir(), 'test_messy_invoice_photo.jpg')
    img.save(out_path, quality=85)
    return out_path

class TestPreprocessing:
    def test_deskew_denoise_produces_readable_text(self):
        path = _make_messy_photo()
        text, method = extract_text(path)
        assert method == 'image_ocr'
        assert 'Office Depot' in text
        assert '508.77' in text
        assert '2 ' in text and '$85.00' in text
        assert '$320.00' in text
        assert '3 ' in text and '$74.97' in text

    def test_preprocess_downscales_oversized_images(self):
        huge = Image.new('RGB', (6000, 8000), color='white')
        cleaned, _ = _preprocess_for_ocr(huge)
        assert max(cleaned.size) <= MAX_IMAGE_DIMENSION

    def test_preprocess_does_not_upscale_small_images(self):
        small = Image.new('RGB', (400, 300), color='white')
        cleaned, _ = _preprocess_for_ocr(small)
        assert cleaned.size[0] <= 400 and cleaned.size[1] <= 300

    def test_preprocess_returns_detected_angle(self):
        img = Image.new('RGB', (800, 600), color='white')
        _, angle = _preprocess_for_ocr(img)
        assert isinstance(angle, float)


class TestExifRotation:
    def test_sideways_stored_photo_is_read_upright(self):
        path = _make_messy_photo()
        img = Image.open(path)
        raw_sensor_pixels = img.rotate(90, expand=True)
        exif = img.getexif()
        exif[0x0112] = 6 # Rotate 90 degrees clockwise to display correctly
        rotated_path = os.path.join(tempfile.gettempdir(), 'test_exif_rotated_invoice.jpg')
        raw_sensor_pixels.save(rotated_path, exif=exif)

        text, _ = extract_text(rotated_path)
        assert '508.77' in text
        assert 'Office Depot' in text


class TestHeicSupport:
    @pytest.mark.skipif(not HEIC_SUPPORTED, reason='pillow-heifnot installed')
    def test_heic_file_is_decoded_and_ocrd(self):
        import pillow_heif
        pillow_heif.register_heif_opener()

        path = _make_messy_photo()
        img = Image.open(path)
        heic_path = os.path.join(tempfile.gettempdir(), 'test_invoice.heic')
        img.save(heic_path, format='HEIF', quality=85)

        text, method = extract_text(heic_path)
        assert method == 'image_ocr'
        assert '508.77' in text
    
    def test_heic_extension_recognized(self):
        from app.services.ocr import IMAGE_EXTENSIONS
        assert '.heic' in IMAGE_EXTENSIONS
        assert '.heif' in IMAGE_EXTENSIONS


class TestExistingBehaviorUnchanged:
    @pytest.mark.parametrize('filename,expected_keywords', [
        ('invoice_cloudhost.pdf', ['CloudHost', '414.60', 'CH-2026-00871']),
        ('invoice_officedepot.pdf', ['Office Depot', '508.77']),
        ('invoice_lawfirm.pdf', ['Brightman', '2100.00'])
    ])
    def test_digital_pdf_still_uses_text_layer(self, filename, expected_keywords):
        path = os.path.join(SAMPLES, filename)
        if not os.path.exists(path):
            pytest.skip(f'Sample missing: {path}')
        text, method = extract_text(path)
        assert method == 'pdf_text_layer'
        for kw in expected_keywords:
            assert kw in text

    def test_unsupported_extension_raises(self):
        with pytest.raises(OCRError):
            extract_text('/tmp/file.docx')