"""Full pipeline on synthetic PDFs: ingest -> (text parse | LLM fallback) -> screen -> rank -> JSON.

No network and no real API key: the LLM is a scripted fake, or the real OpenRouterClient over a
mocked HTTP transport.
"""
import json
import re

import httpx

from src.extraction import ResumeExtractor
from src.llm import OpenRouterClient
from src.models import ScreeningStatus
from src.pipeline import run_batch, write_summary

from .llm_fakes import FakeLLM, as_json, strong_extraction, timeout_error
from .pdf_fixtures import LINES, RESUME_LINES, make_pdf, make_scanned_pdf


def by_file(summary):
    return {r.source_file: r for r in summary.results}


def text_resume(path, python="Python"):
    make_pdf(path, [l.replace("Python", python) for l in RESUME_LINES])


def test_normal_text_pdf_never_calls_the_llm(tmp_path):
    text_resume(tmp_path / "digital.pdf")
    llm = FakeLLM()
    summary = run_batch(tmp_path, ResumeExtractor(llm))
    r = by_file(summary)["digital.pdf"]
    assert llm.calls == []
    assert r.status is ScreeningStatus.RANKED and r.candidate.extraction_method == "text"
    assert r.score.total > 0 and summary.llm_fallback_extractions == 0


def test_scanned_pdf_invokes_the_llm_fallback_and_is_screened_deterministically(tmp_path):
    make_scanned_pdf(tmp_path / "scan.pdf", LINES)
    llm = FakeLLM()
    summary = run_batch(tmp_path, ResumeExtractor(llm))
    r = by_file(summary)["scan.pdf"]
    assert len(llm.calls) == 1 and summary.llm_fallback_extractions == 1
    assert r.status is ScreeningStatus.RANKED and r.candidate.extraction_method == "llm_vision"
    assert r.eligibility.eligible and r.score.ai_project_depth > 0 and r.score.github_activity == 0
    assert r.rank == 1


def test_text_pdf_without_recognisable_sections_falls_back_to_llm(tmp_path):
    make_pdf(tmp_path / "odd.pdf", [f"Selected Work item {i}: built a Python RAG chatbot with FAISS" for i in range(8)])
    llm = FakeLLM()
    run_batch(tmp_path, ResumeExtractor(llm))
    assert len(llm.calls) == 1


def test_llm_failures_are_isolated_per_candidate(tmp_path):
    text_resume(tmp_path / "a_digital.pdf")
    make_scanned_pdf(tmp_path / "b_scan_timeout.pdf", LINES)
    make_scanned_pdf(tmp_path / "c_scan_ratelimit.pdf", LINES + ["x"])
    make_scanned_pdf(tmp_path / "d_scan_garbage.pdf", LINES + ["y"])
    (tmp_path / "e_broken.pdf").write_bytes(b"not a pdf")
    llm = FakeLLM(timeout_error(), RuntimeError("unexpected"), "garbage", "garbage")
    summary = run_batch(tmp_path, ResumeExtractor(llm))
    got = by_file(summary)
    assert got["a_digital.pdf"].status is ScreeningStatus.RANKED
    assert "timed out" in got["b_scan_timeout.pdf"].error
    assert "RuntimeError" in got["c_scan_ratelimit.pdf"].error
    assert "invalid structured output" in got["d_scan_garbage.pdf"].error
    assert got["e_broken.pdf"].status is ScreeningStatus.FAILED
    assert (summary.ranked, summary.failed) == (1, 4)


def test_http_429_through_the_real_client_fails_only_that_candidate(tmp_path):
    text_resume(tmp_path / "a_digital.pdf")
    make_scanned_pdf(tmp_path / "b_scan.pdf", LINES)
    client = OpenRouterClient("sk-or-x", http=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(429, json={"error": {"message": "rate limited"}}))))
    summary = run_batch(tmp_path, ResumeExtractor(client))
    got = by_file(summary)
    assert got["a_digital.pdf"].status is ScreeningStatus.RANKED
    assert got["b_scan.pdf"].status is ScreeningStatus.FAILED and "429" in got["b_scan.pdf"].error


def test_without_an_api_key_only_fallback_candidates_fail(tmp_path):
    text_resume(tmp_path / "a_digital.pdf")
    make_scanned_pdf(tmp_path / "b_scan.pdf", LINES)
    got = by_file(run_batch(tmp_path, ResumeExtractor(None)))
    assert got["a_digital.pdf"].status is ScreeningStatus.RANKED
    assert "OPENROUTER_API_KEY" in got["b_scan.pdf"].error


def test_rejected_candidates_have_no_score_or_rank_and_duplicates_are_skipped(tmp_path):
    text_resume(tmp_path / "a.pdf")
    (tmp_path / "a_copy.pdf").write_bytes((tmp_path / "a.pdf").read_bytes())
    make_pdf(tmp_path / "java.pdf", [re.sub(r"Python|FastAPI|FAISS|LangChain|OpenAI|RAG", "Java", l)
                                     for l in RESUME_LINES])
    summary = run_batch(tmp_path, ResumeExtractor(FakeLLM()))
    java = by_file(summary)["java.pdf"]
    assert java.status is ScreeningStatus.REJECTED and java.score is None and java.rank is None
    assert java.eligibility.rejection_reasons
    assert summary.duplicates_skipped == 1 and summary.total_files == 3


def test_results_are_deterministic_across_runs(tmp_path):
    text_resume(tmp_path / "a.pdf")
    make_scanned_pdf(tmp_path / "b.pdf", LINES)

    def run():
        s = run_batch(tmp_path, ResumeExtractor(FakeLLM()))
        return s.model_copy(update={"duration_seconds": 0}).model_dump()

    assert run() == run()


def test_openrouter_response_flows_through_the_real_client(tmp_path):
    make_scanned_pdf(tmp_path / "scan.pdf", LINES)
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": as_json(strong_extraction())}}]})

    client = OpenRouterClient("sk-or-x", http=httpx.Client(transport=httpx.MockTransport(handler)))
    summary = run_batch(tmp_path, ResumeExtractor(client))
    assert summary.ranked == 1 and len(bodies) == 1
    assert any(p["type"] == "image_url" for p in bodies[0]["messages"][1]["content"])


def test_no_secret_or_raw_text_in_output_file(tmp_path, capsys):
    secret = "sk-or-SUPER-SECRET-VALUE"
    make_scanned_pdf(tmp_path / "scan.pdf", LINES)
    text_resume(tmp_path / "ok.pdf")
    handler = lambda r: httpx.Response(401, json={"error": {"message": "bad credentials"}})  # noqa: E731
    client = OpenRouterClient(secret, http=httpx.Client(transport=httpx.MockTransport(handler)))
    summary = run_batch(tmp_path, ResumeExtractor(client))
    out = tmp_path / "out" / "results.json"
    write_summary(summary, out)
    text = out.read_text()
    assert secret not in text and "raw_text" not in text
    seen = capsys.readouterr()
    assert secret not in seen.out and secret not in seen.err
