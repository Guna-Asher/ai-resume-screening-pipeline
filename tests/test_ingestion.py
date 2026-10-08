import pytest

from src.ingestion import render_pages
from src.models import IngestionStatus, ScreeningStatus
from src.pipeline import failures_from_ingestion

from .pdf_fixtures import LINES, ingest_dir, make_pdf, make_scanned_pdf


def test_duplicate_files_detected(tmp_path):
    make_pdf(tmp_path / "a.pdf", LINES)
    (tmp_path / "b.pdf").write_bytes((tmp_path / "a.pdf").read_bytes())
    docs = {d.source_file: d for d in ingest_dir(tmp_path)}
    assert docs["a.pdf"].status is IngestionStatus.OK and "Python RAG agent" in docs["a.pdf"].text
    assert docs["b.pdf"].status is IngestionStatus.DUPLICATE and docs["b.pdf"].duplicate_of == "a.pdf"


def test_malformed_pdf_does_not_crash_batch(tmp_path):
    make_pdf(tmp_path / "good.pdf", LINES)
    (tmp_path / "bad.pdf").write_bytes(b"this is not a pdf")
    (tmp_path / "empty.pdf").write_bytes(b"")
    make_pdf(tmp_path / "scanned.pdf", ["x"])  # valid but almost no text
    docs = {d.source_file: d for d in ingest_dir(tmp_path)}
    assert docs["good.pdf"].status is IngestionStatus.OK
    assert docs["bad.pdf"].status is IngestionStatus.ERROR
    assert docs["empty.pdf"].status is IngestionStatus.ERROR
    assert docs["scanned.pdf"].status is IngestionStatus.NEEDS_FALLBACK
    failed = failures_from_ingestion(list(docs.values()))
    assert {r.source_file for r in failed} == {"bad.pdf", "empty.pdf"}   # scanned -> extractor, not failure
    assert all(r.status is ScreeningStatus.FAILED for r in failed)


def test_image_only_and_garbled_pdfs_need_fallback_and_carry_their_path(tmp_path):
    make_scanned_pdf(tmp_path / "scan.pdf", LINES)
    make_pdf(tmp_path / "garbled.pdf", ["(cid:12)(cid:7) 1234567890 ###" for _ in range(20)])
    docs = {d.source_file: d for d in ingest_dir(tmp_path)}
    assert docs["scan.pdf"].status is IngestionStatus.NEEDS_FALLBACK and docs["scan.pdf"].text == ""
    assert docs["garbled.pdf"].status is IngestionStatus.NEEDS_FALLBACK
    assert docs["scan.pdf"].path == str(tmp_path / "scan.pdf")


def test_pages_render_locally_to_jpeg_and_are_capped(tmp_path):
    make_scanned_pdf(tmp_path / "scan.pdf", LINES)
    pages = render_pages(str(tmp_path / "scan.pdf"))
    assert len(pages) == 1 and pages[0].startswith(b"\xff\xd8")


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text

    def get(self, key):
        return None


class _FakeReader:
    def __init__(self, text):
        self.is_encrypted = False
        self.pages = [_FakePage(text)]


FRAGMENTED = "\n \n".join("Built a Python RAG agent using LangChain and FAISS for question answering".split() * 6)
HEALTHY = "\n".join(["Built a Python RAG agent using LangChain and FAISS for question answering"] * 6)


def test_fragmented_pypdf_text_is_replaced_by_pymupdf_text(monkeypatch):
    from src.ingestion import pdf
    monkeypatch.setattr(pdf, "PdfReader", lambda _: _FakeReader(FRAGMENTED))
    monkeypatch.setattr(pdf, "_pymupdf_text", lambda _: HEALTHY)
    assert pdf._extract_text(b"x")[0] == HEALTHY


def test_healthy_pypdf_text_is_left_alone_and_a_worse_alternative_is_ignored(monkeypatch):
    from src.ingestion import pdf
    monkeypatch.setattr(pdf, "PdfReader", lambda _: _FakeReader(HEALTHY))
    monkeypatch.setattr(pdf, "_pymupdf_text", lambda _: pytest.fail("must not be consulted"))
    assert pdf._extract_text(b"x")[0] == HEALTHY
    monkeypatch.setattr(pdf, "PdfReader", lambda _: _FakeReader(FRAGMENTED))
    monkeypatch.setattr(pdf, "_pymupdf_text", lambda _: FRAGMENTED)
    assert pdf._extract_text(b"x")[0] == FRAGMENTED.strip()
