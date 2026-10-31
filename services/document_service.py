"""Document utilities: extension validation, text extraction, image OCR/compression, cleanup."""

import base64
import io
import logging
import os
import time

from PIL import Image

import config
from services.extractor_service import ExtractorFactory

logger = logging.getLogger(__name__)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS


def is_image_file(filepath):
    ext = filepath.rsplit(".", 1)[1].lower() if "." in filepath else ""
    return ext in config.IMAGE_EXTENSIONS


def extract_text_from_image_ocr(filepath):
    """Extract text from image using Tesseract OCR."""
    extractor = ExtractorFactory.get_extractor(filepath)
    if extractor:
        try:
            text = extractor.extract(filepath)
            return text if text else None
        except Exception as e:
            return f"OCR Error: {e!s}"
    return None


def extract_text_from_file(filepath):
    try:
        extractor = ExtractorFactory.get_extractor(filepath)
        if not extractor:
            return None
        # Image extraction is handled by vision model directly unless falling back to OCR,
        # which is checked explicitly in celery task or done via extract_text_from_image_ocr.
        # But if called directly, we extract:
        if is_image_file(filepath):
            return None
        return extractor.extract(filepath)
    except Exception as e:
        return f"Error extracting text: {e!s}"


def resize_and_compress_image(filepath, max_size=None, quality=None):
    """Resize image to reduce base64 size."""
    if max_size is None:
        max_size = config.IMAGE_COMPRESS_MAX_SIZE
    if quality is None:
        quality = config.IMAGE_COMPRESS_QUALITY
    try:
        with Image.open(filepath) as source_img:
            img = source_img
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        logger.exception(f"Error compressing image: {e}")
        return None


def cleanup_old_uploads(upload_dir):
    try:
        now = time.time()
        for filename in os.listdir(upload_dir):
            filepath = os.path.join(upload_dir, filename)
            is_old_file = os.path.isfile(filepath) and os.stat(filepath).st_mtime < now - config.CLEANUP_EXPIRE_SECONDS
            if is_old_file:
                os.remove(filepath)
                logger.info(f"Cleaned up old file: {filename}")
    except Exception as e:
        logger.error(f"Error in cleanup: {e}")
