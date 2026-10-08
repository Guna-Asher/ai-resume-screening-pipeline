"""Render PDF pages to images locally (PyMuPDF bundles MuPDF; no system packages needed)."""
import pymupdf

MAX_PAGES = 4   # resumes are 1-3 pages; cap cost and request size
RENDER_DPI = 150
JPEG_QUALITY = 85
IMAGE_MIME = "image/jpeg"


def render_pages(path: str, max_pages: int = MAX_PAGES) -> list[bytes]:
    """Return one JPEG per page (first `max_pages` only). Raises on unreadable PDFs."""
    with pymupdf.open(path) as pdf:
        if pdf.page_count == 0:
            raise ValueError("PDF has no pages")
        return [page.get_pixmap(dpi=RENDER_DPI).tobytes("jpeg", jpg_quality=JPEG_QUALITY)
                for page in list(pdf)[:max_pages]]
