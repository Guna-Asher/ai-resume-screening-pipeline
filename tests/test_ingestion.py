from pathlib import Path

from src.ingestion import ingest_directory
from src.models import IngestionStatus, ScreeningStatus
from src.pipeline import failures_from_ingestion


def make_pdf(path: Path, lines: list[str]) -> None:
    """Write a minimal single-page text PDF (no third-party PDF writer needed)."""
    stream = "BT /F1 10 Tf 12 TL 40 760 Td " + " ".join(f"({l}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    path.write_bytes(out)


LINES = [f"Line {i} Built a Python RAG agent with FastAPI and PostgreSQL" for i in range(8)]


def test_duplicate_files_detected(tmp_path):
    make_pdf(tmp_path / "a.pdf", LINES)
    (tmp_path / "b.pdf").write_bytes((tmp_path / "a.pdf").read_bytes())
    docs = {d.source_file: d for d in ingest_directory(tmp_path)}
    assert docs["a.pdf"].status is IngestionStatus.OK and "Python RAG agent" in docs["a.pdf"].text
    assert docs["b.pdf"].status is IngestionStatus.DUPLICATE and docs["b.pdf"].duplicate_of == "a.pdf"


def test_malformed_pdf_does_not_crash_batch(tmp_path):
    make_pdf(tmp_path / "good.pdf", LINES)
    (tmp_path / "bad.pdf").write_bytes(b"this is not a pdf")
    (tmp_path / "empty.pdf").write_bytes(b"")
    make_pdf(tmp_path / "scanned.pdf", ["x"])  # valid but almost no text
    docs = {d.source_file: d for d in ingest_directory(tmp_path)}
    assert docs["good.pdf"].status is IngestionStatus.OK
    assert docs["bad.pdf"].status is IngestionStatus.ERROR
    assert docs["empty.pdf"].status is IngestionStatus.ERROR
    assert docs["scanned.pdf"].status is IngestionStatus.NEEDS_FALLBACK
    failed = failures_from_ingestion(list(docs.values()))
    assert {r.source_file for r in failed} == {"bad.pdf", "empty.pdf", "scanned.pdf"}
    assert all(r.status is ScreeningStatus.FAILED for r in failed)
