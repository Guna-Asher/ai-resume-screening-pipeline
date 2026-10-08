"""Synthetic PDFs: a digital text PDF and an image-only ("scanned") PDF."""
from pathlib import Path

import pymupdf


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path: Path, lines: list[str]) -> None:
    """Write a minimal single-page text PDF (no third-party PDF writer needed)."""
    stream = "BT /F1 10 Tf 12 TL 40 760 Td " + " ".join(f"({_esc(l)}) Tj T*" for l in lines) + " ET"
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


def make_scanned_pdf(path: Path, lines: list[str]) -> None:
    """A PDF whose only content is a picture of the text: pypdf finds no text layer."""
    src_path = path.with_name(path.stem + ".src.pdf")
    make_pdf(src_path, lines)
    with pymupdf.open(src_path) as src:
        png = src[0].get_pixmap(dpi=100).tobytes("png")
    src_path.unlink()
    out = pymupdf.open()
    page = out.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=png)
    out.save(path)
    out.close()


LINES = [f"Line {i} Built a Python RAG agent with FastAPI and PostgreSQL" for i in range(8)]

RESUME_LINES = [
    "Asha Verma",
    "asha.verma@example.com | github.com/asha-verma | Bengaluru",
    "",
    "SKILLS",
    "Languages: Python, SQL, JavaScript",
    "Frameworks: FastAPI, LangChain, React",
    "",
    "PROJECTS",
    "Resume Screener | Python, FastAPI, FAISS",
    "- Built a RAG pipeline using OpenAI embeddings and FAISS to rank",
    "candidates against job descriptions.",
    "- Implemented tool calling for a multi-step agent workflow with evaluation checks.",
    "",
    "Portfolio Site",
    "- Designed a static personal website with React.",
    "",
    "EXPERIENCE",
    "Software Engineer Intern | Acme Corp | Jun 2024 - Aug 2024",
    "- Developed REST endpoints in FastAPI backed by PostgreSQL and deployed them to AWS with Docker.",
    "- Wrote pytest unit tests and added retry logic for flaky vendor APIs.",
    "",
    "EDUCATION",
    "B.Tech Computer Science, Example Institute of Technology, 2021 - 2025",
]
