"""Thin HTTP wrapper around the same pipeline the CLI uses. No screening logic lives here."""
import logging
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response

from src.ingestion import InputLimits
from src.models import BatchSummary
from src.pipeline import screen_inputs, summary_json

logger = logging.getLogger("screening.web")
INDEX_HTML = Path(__file__).with_name("index.html")
ALLOWED = {".pdf", ".zip"}
CHUNK = 64 * 1024

Runner = Callable[[Sequence[Path], InputLimits], BatchSummary]


def _safe_name(raw: str | None) -> str:
    return PurePosixPath((raw or "").replace("\\", "/")).name[:120]


def _save(upload: UploadFile, dest: Path, cap: int, total_so_far: int, limits: InputLimits) -> int:
    """Stream an upload to disk, enforcing the per-file and per-request caps. Returns bytes written."""
    written = 0
    dest.parent.mkdir(parents=True)
    with open(dest, "wb") as out:
        while chunk := upload.file.read(CHUNK):
            written += len(chunk)
            if written > cap or total_so_far + written > limits.max_upload_bytes:
                raise HTTPException(413, f"{dest.name!r} is too large (limit {cap // (1024 * 1024)} MB per file, "
                                         f"{limits.max_upload_bytes // (1024 * 1024)} MB per request)")
            out.write(chunk)
    return written


def create_app(runner: Runner | None = None, limits: InputLimits | None = None) -> FastAPI:
    limits = limits or InputLimits.from_env()
    run: Runner = runner or (lambda paths, lim: screen_inputs(list(paths), lim))
    app = FastAPI(title="AI Resume Screening", docs_url=None, redoc_url=None, openapi_url=None)
    page = INDEX_HTML.read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return page

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/screen")
    def screen(request: Request, files: list[UploadFile] | None = File(None)) -> Response:
        if not files:
            raise HTTPException(400, "No files uploaded. Choose one or more PDF or ZIP files.")
        if len(files) > limits.max_upload_files:
            raise HTTPException(413, f"Too many files (maximum {limits.max_upload_files} per request).")
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limits.max_upload_bytes + 1024 * 1024:
            raise HTTPException(413, f"Upload too large (maximum {limits.max_upload_bytes // (1024 * 1024)} MB).")
        names = [_safe_name(f.filename) for f in files]
        for name in names:
            if Path(name).suffix.lower() not in ALLOWED:
                raise HTTPException(400, f"Unsupported file type: {name or '(no name)'}. Only PDF and ZIP are accepted.")

        with tempfile.TemporaryDirectory(prefix="upload-") as tmp:
            paths, total = [], 0
            for i, (upload, name) in enumerate(zip(files, names)):
                is_zip = name.lower().endswith(".zip")
                cap = limits.max_archive_bytes if is_zip else limits.max_file_bytes
                dest = Path(tmp) / str(i) / name
                total += _save(upload, dest, cap, total, limits)
                paths.append(dest)
            try:
                summary = run(paths, limits)
            except Exception as e:   # never leak internals to the client; log only the exception type
                logger.error("screening failed: %s", type(e).__name__)
                raise HTTPException(500, "Screening failed unexpectedly. Please try again.") from None
        return Response(summary_json(summary), media_type="application/json")

    return app


app = create_app()
