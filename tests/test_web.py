"""Web API: thin wrapper over the same pipeline. Fake extractor/enricher services, no network."""
import json
import tempfile

import pytest
from fastapi.testclient import TestClient

from src.extraction import ResumeExtractor
from src.ingestion import InputLimits
from src.pipeline import render_text, run_batch, summary_json
from src.web.app import create_app

from .pdf_fixtures import RESUME_LINES, make_zip, pdf_bytes


def offline_runner(paths, limits):
    return run_batch(list(paths), ResumeExtractor(None), None, limits)


@pytest.fixture
def client():
    return TestClient(create_app(runner=offline_runner, limits=InputLimits()))


@pytest.fixture
def pdf(tmp_path):
    return pdf_bytes(tmp_path)


def up(name, data, mime="application/pdf"):
    return ("files", (name, data, mime))


def test_health_and_index(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/")
    assert r.status_code == 200 and "AI Resume Screening" in r.text and "Run Screening" in r.text


def test_only_the_three_routes_exist(client):
    for path in ("/docs", "/openapi.json", "/redoc", "/api/screen-other"):
        assert client.get(path).status_code == 404
    assert client.get("/api/screen").status_code == 405


def test_single_pdf_returns_structured_summary(client, pdf):
    r = client.post("/api/screen", files=[up("asha.pdf", pdf)])
    body = r.json()
    assert r.status_code == 200 and r.headers["content-type"] == "application/json"
    assert (body["total_files"], body["ranked"], body["rejected"], body["failed"]) == (1, 1, 0, 0)
    res = body["results"][0]
    assert res["rank"] == 1 and set(res["score"]) >= {"ai_project_depth", "python_backend", "cloud_fullstack",
                                                      "github_activity", "engineering_depth", "total"}
    assert "raw_text" not in r.text


def test_multiple_pdfs_zip_and_mixed_uploads(client, tmp_path, pdf):
    other = pdf_bytes(tmp_path, RESUME_LINES + ["- Built a Python service."])
    r = client.post("/api/screen", files=[up("a.pdf", pdf), up("b.pdf", other)])
    assert r.json()["ranked"] == 2

    make_zip(tmp_path / "z.zip", {"x/one.pdf": pdf, "x/two.pdf": other})
    z = (tmp_path / "z.zip").read_bytes()
    assert client.post("/api/screen", files=[up("z.zip", z, "application/zip")]).json()["total_files"] == 2

    mixed = client.post("/api/screen", files=[up("a.pdf", pdf), up("z.zip", z, "application/zip")]).json()
    assert mixed["total_files"] == 3 and mixed["duplicates_skipped"] == 1 and mixed["ranked"] == 2


def test_invalid_uploads_get_safe_errors(client, pdf):
    cases = [
        (client.post("/api/screen"), 400, "No files"),
        (client.post("/api/screen", files=[up("evil.exe", b"MZ")]), 400, "Unsupported file type"),
        (client.post("/api/screen", files=[up("a.pdf", pdf), up("notes.txt", b"x", "text/plain")]), 400, "notes.txt"),
    ]
    for resp, status, text in cases:
        assert resp.status_code == status and text in resp.json()["detail"]
        assert "Traceback" not in resp.text


def test_corrupt_pdf_is_a_failed_candidate_not_an_http_error(client, pdf):
    body = client.post("/api/screen", files=[up("good.pdf", pdf), up("bad.pdf", b"nope")]).json()
    assert (body["ranked"], body["failed"]) == (1, 1)


def test_size_and_count_limits():
    small = TestClient(create_app(runner=offline_runner, limits=InputLimits(max_upload_files=2, max_file_bytes=1000,
                                                                              max_archive_bytes=1000, max_upload_bytes=5000)))
    assert small.post("/api/screen", files=[up(f"{i}.pdf", b"x") for i in range(3)]).status_code == 413
    assert small.post("/api/screen", files=[up("big.pdf", b"x" * 1001)]).status_code == 413
    assert small.post("/api/screen", files=[up("big.zip", b"x" * 1001)]).status_code == 413


def test_unexpected_server_error_is_generic(pdf):
    def boom(paths, limits):
        raise RuntimeError("secret internal detail /etc/passwd")
    c = TestClient(create_app(runner=boom, limits=InputLimits()))
    r = c.post("/api/screen", files=[up("a.pdf", pdf)])
    assert r.status_code == 500 and "secret" not in r.text and "passwd" not in r.text


def test_upload_filename_cannot_escape_the_workspace(pdf):
    seen = []

    def spy(paths, limits):
        seen.extend(paths)
        return offline_runner(paths, limits)
    c = TestClient(create_app(runner=spy, limits=InputLimits()))
    assert c.post("/api/screen", files=[up("../../../evil.pdf", pdf)]).status_code == 200
    assert seen[0].name == "evil.pdf" and "upload-" in str(seen[0])


def test_upload_workspace_is_cleaned_up(client, pdf, tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"; scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    client.post("/api/screen", files=[up("a.pdf", pdf)])
    assert list(scratch.iterdir()) == []


def test_web_and_cli_produce_the_same_result(client, tmp_path, pdf):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "asha.pdf").write_bytes(pdf)
    cli = json.loads(summary_json(offline_runner([tmp_path / "in"], InputLimits())))
    web = client.post("/api/screen", files=[up("asha.pdf", pdf)]).json()
    for d in (cli, web):
        d["duration_seconds"] = 0
    assert cli == web


def test_text_report_is_a_rendering_of_the_same_summary(tmp_path, pdf):
    (tmp_path / "a.pdf").write_bytes(pdf)
    (tmp_path / "bad.pdf").write_bytes(b"x")
    summary = offline_runner([tmp_path], InputLimits())
    text = render_text(summary)
    assert "Ranked: 1" in text and "a.pdf" in text and "bad.pdf" in text and "FAILED" in text
