"""Deterministic PDF ingestion: discover, hash, dedupe, extract text. Never raises per file."""
import hashlib
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from src.models import IngestedDocument, IngestionStatus

MIN_TEXT_CHARS = 200      # below this the PDF is likely scanned/image-only -> needs fallback
MIN_ALPHA_RATIO = 0.5     # garbled font encodings extract as "(cid:12)" / symbol soup


def is_usable_text(text: str) -> bool:
    """Is pypdf's output good enough to parse deterministically?"""
    stripped = "".join(text.split())
    if len(text.strip()) < MIN_TEXT_CHARS or not stripped:
        return False
    return sum(c.isalpha() for c in stripped) / len(stripped) >= MIN_ALPHA_RATIO


def discover_pdfs(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    return sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def _extract_text(data: bytes) -> tuple[str, int]:
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF is encrypted")
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip(), len(reader.pages)


def ingest_directory(input_dir: Path) -> list[IngestedDocument]:
    docs: list[IngestedDocument] = []
    seen: dict[str, str] = {}  # content hash -> first file name
    for path in discover_pdfs(input_dir):
        docs.append(_ingest_one(path, seen))
    return docs


def _ingest_one(path: Path, seen: dict[str, str]) -> IngestedDocument:
    name = path.name
    try:
        data = path.read_bytes()
    except OSError as e:
        return IngestedDocument(source_file=name, status=IngestionStatus.ERROR, error=f"read failed: {e}")

    digest = hashlib.sha256(data).hexdigest()
    if digest in seen:
        return IngestedDocument(source_file=name, status=IngestionStatus.DUPLICATE,
                                content_hash=digest, duplicate_of=seen[digest])
    seen[digest] = name

    try:
        text, pages = _extract_text(data)
    except Exception as e:  # pypdf raises many types for malformed input
        return IngestedDocument(source_file=name, status=IngestionStatus.ERROR,
                                content_hash=digest, error=f"unreadable PDF: {type(e).__name__}: {e}")

    status = IngestionStatus.OK if is_usable_text(text) else IngestionStatus.NEEDS_FALLBACK
    return IngestedDocument(source_file=name, path=str(path), status=status, content_hash=digest,
                            text=text, page_count=pages)
