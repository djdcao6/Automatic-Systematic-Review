import io
import uuid
from pathlib import Path

import pdfplumber

from asr_backend import upload_limits
from asr_backend.settings import settings

PARSED = "parsed"
PARSE_FAILED = "parse_failed"

# The PDF spec lets the header sit anywhere in the first 1024 bytes, and real
# files do have stray bytes before it.
PDF_MAGIC = b"%PDF-"
PDF_MAGIC_WINDOW = 1024


class PdfParseError(Exception):
    """Raised when a PDF cannot be opened or read for text."""


class PdfTooManyPages(Exception):
    def __init__(self, limit: int):
        super().__init__(f"PDF has more than {limit} pages, which is the limit.")


def extract_text(pdf_bytes: bytes) -> tuple[str | None, str]:
    """Extract text from a PDF's bytes.

    Returns (parsed_text, parse_status). A PDF with no extractable text layer
    (e.g. a scan) or one that fails to open is flagged parse_failed rather
    than raising, since it still needs to be stored for manual entry.

    Raises PdfTooManyPages for a PDF over the page limit, before reading any page.
    """
    try:
        text = _read_pages(pdf_bytes)
    except PdfParseError:
        return None, PARSE_FAILED

    if not text:
        return None, PARSE_FAILED
    return text, PARSED


def _read_pages(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if len(pdf.pages) > upload_limits.MAX_PDF_PAGES:
                raise PdfTooManyPages(upload_limits.MAX_PDF_PAGES)
            pages_text = [page.extract_text() or "" for page in pdf.pages]
    except PdfTooManyPages:
        raise
    except Exception as exc:
        raise PdfParseError(f"Failed to parse PDF: {exc}") from exc
    return "\n\n".join(page_text for page_text in pages_text if page_text).strip()


def is_pdf_upload(filename: str | None, content_type: str | None) -> bool:
    if content_type == "application/pdf":
        return True
    return bool(filename) and filename.lower().endswith(".pdf")


def has_pdf_header(content: bytes) -> bool:
    return PDF_MAGIC in content[:PDF_MAGIC_WINDOW]


def save_pdf(citation_id: uuid.UUID, content: bytes) -> str:
    root = Path(settings.full_text_storage_path)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{citation_id}.pdf"
    path.write_bytes(content)
    return str(path)
