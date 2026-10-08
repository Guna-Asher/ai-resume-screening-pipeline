"""Deterministic PDF ingestion: discover, hash, dedupe, extract text. Never raises per file."""
import hashlib
import re
from io import BytesIO

import pymupdf
from pypdf import PdfReader

from src.models import IngestedDocument, IngestionStatus

from .inputs import PdfInput

MIN_TEXT_CHARS = 200      # below this the PDF is likely scanned/image-only -> needs fallback
MIN_ALPHA_RATIO = 0.5     # garbled font encodings extract as "(cid:12)" / symbol soup
MIN_WORDS_PER_LINE = 3.0  # pypdf sometimes emits one word per line; real resume lines average 6-12
_GITHUB_URI = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9][A-Za-z0-9-]*", re.I)



def is_usable_text(text: str) -> bool:
    """Is pypdf's output good enough to parse deterministically?"""
    stripped = "".join(text.split())
    if len(text.strip()) < MIN_TEXT_CHARS or not stripped:
        return False
    return sum(c.isalpha() for c in stripped) / len(stripped) >= MIN_ALPHA_RATIO


def _words_per_line(text: str) -> float:
    lines = [ln.split() for ln in text.splitlines() if ln.strip()]
    return sum(len(ln) for ln in lines) / len(lines) if lines else 0.0


def _pymupdf_text(data: bytes) -> str:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc).strip()


def _extract_text(data: bytes) -> tuple[str, int, list[str]]:
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF is encrypted")
    pages, links = [], []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
        for annot in page.get("/Annots") or []:  # hyperlinks: "GitHub" text hiding a URL
            try:
                uri = str(annot.get_object().get("/A", {}).get("/URI", ""))
            except Exception:  # a malformed annotation must not lose the whole resume
                continue
            if _GITHUB_URI.match(uri) and uri not in links:
                links.append(uri)
    text = "\n".join(pages).strip()
    if text and _words_per_line(text) < MIN_WORDS_PER_LINE:
        # pypdf lost the line structure the parser depends on; PyMuPDF usually keeps it
        try:
            alt = _pymupdf_text(data)
            if _words_per_line(alt) > _words_per_line(text):
                text = alt
        except (RuntimeError, ValueError):
            pass
    return text, len(reader.pages), links


def ingest_paths(inputs: list[PdfInput]) -> list[IngestedDocument]:
    docs: list[IngestedDocument] = []
    seen: dict[str, str] = {}  # content hash -> first file name
    for item in inputs:
        docs.append(_ingest_one(item, seen))
    return docs


def _ingest_one(item: PdfInput, seen: dict[str, str]) -> IngestedDocument:
    name, path = item.name, item.path
    try:
        data = path.read_bytes()
    except OSError as e:
        return IngestedDocument(source_file=name, status=IngestionStatus.ERROR, error=f"read failed: {e}",
                                error_code="file_unreadable")

    digest = hashlib.sha256(data).hexdigest()
    if digest in seen:
        return IngestedDocument(source_file=name, status=IngestionStatus.DUPLICATE,
                                content_hash=digest, duplicate_of=seen[digest])
    seen[digest] = name

    try:
        text, pages, links = _extract_text(data)
    except Exception as e:  # pypdf raises many types for malformed input
        return IngestedDocument(source_file=name, status=IngestionStatus.ERROR,
                                content_hash=digest, error=f"unreadable PDF: {type(e).__name__}: {e}",
                                error_code="unreadable_pdf")

    status = IngestionStatus.OK if is_usable_text(text) else IngestionStatus.NEEDS_FALLBACK
    if links and status is IngestionStatus.OK and not _GITHUB_URI.search(text):
        text += "\nLinks\n" + "\n".join(links)  # visible to the parser and to evidence grounding
    return IngestedDocument(source_file=name, path=str(path), status=status, content_hash=digest,
                            text=text, page_count=pages)
