import docx
import pypdf
import pytesseract
from PIL import Image


class BaseExtractor:
    def extract(self, filepath: str) -> str:
        raise NotImplementedError("Each extractor must implement extract method")

class PlainTextExtractor(BaseExtractor):
    def extract(self, filepath: str) -> str:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

class PdfExtractor(BaseExtractor):
    def extract(self, filepath: str) -> str:
        pages = []
        with open(filepath, 'rb') as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                pages.append(page.extract_text() or "")
        return "\n".join(pages)

class DocxExtractor(BaseExtractor):
    def extract(self, filepath: str) -> str:
        doc = docx.Document(filepath)
        return "\n".join([para.text for para in doc.paragraphs])

class ImageOcrExtractor(BaseExtractor):
    def extract(self, filepath: str) -> str:
        try:
            img = Image.open(filepath)
            text = pytesseract.image_to_string(img, lang='vie+eng')
            return text.strip() if text.strip() else ""
        except Exception as e:
            return f"OCR Error: {e!s}"

class ExtractorFactory:
    _extractors = {
        'txt': PlainTextExtractor(),
        'md': PlainTextExtractor(),
        'csv': PlainTextExtractor(),
        'json': PlainTextExtractor(),
        'xml': PlainTextExtractor(),
        'yaml': PlainTextExtractor(),
        'yml': PlainTextExtractor(),
        'pdf': PdfExtractor(),
        'docx': DocxExtractor(),
        'doc': DocxExtractor(),
        'png': ImageOcrExtractor(),
        'jpg': ImageOcrExtractor(),
        'jpeg': ImageOcrExtractor(),
        'gif': ImageOcrExtractor(),
        'bmp': ImageOcrExtractor(),
        'tiff': ImageOcrExtractor(),
        'tif': ImageOcrExtractor(),
        'webp': ImageOcrExtractor()
    }

    @classmethod
    def get_extractor(cls, filepath: str) -> BaseExtractor:
        ext = filepath.rsplit('.', 1)[1].lower() if '.' in filepath else ''
        return cls._extractors.get(ext)
