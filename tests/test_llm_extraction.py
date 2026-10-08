import pytest

from src.extraction import ExtractionError, ground_resume, extract_with_llm
from src.models import ExtractedResume, IngestionStatus
from src.screening import check_eligibility, score_resume

from .llm_fakes import FakeLLM, as_json, strong_extraction, timeout_error
from .pdf_fixtures import LINES, ingest_dir, make_scanned_pdf


@pytest.fixture
def scanned_doc(tmp_path):
    make_scanned_pdf(tmp_path / "scan.pdf", LINES)
    doc = ingest_dir(tmp_path)[0]
    assert doc.status is IngestionStatus.NEEDS_FALLBACK   # image-only PDF: pypdf finds no text
    return doc


def test_valid_structured_extraction(scanned_doc):
    llm = FakeLLM()
    r = extract_with_llm(scanned_doc, llm)
    assert isinstance(r, ExtractedResume) and r.extraction_method == "llm_vision"
    assert r.source_file == "scan.pdf" and r.github_username == "asha-verma"
    assert [p.name for p in r.projects] == ["Resume Screener"]
    assert len(llm.calls) == 1 and len(llm.calls[0]["images"]) == 1
    assert llm.calls[0]["images"][0].data.startswith(b"\xff\xd8")   # JPEG rendered locally


def test_invalid_json_then_valid_retries_once(scanned_doc):
    llm = FakeLLM("{not json", as_json(strong_extraction()))
    assert extract_with_llm(scanned_doc, llm).name == "Asha Verma"
    assert len(llm.calls) == 2
    assert "rejected" in llm.calls[1]["user_text"] and "rejected" not in llm.calls[0]["user_text"]


def test_schema_violation_then_valid_retries_once(scanned_doc):
    llm = FakeLLM(as_json(strong_extraction(skills="python")), as_json(strong_extraction()))
    assert extract_with_llm(scanned_doc, llm).skills[0] == "Python"
    assert len(llm.calls) == 2


def test_invalid_twice_fails_after_exactly_one_retry(scanned_doc):
    llm = FakeLLM("nope", "still nope", as_json(strong_extraction()))
    with pytest.raises(ExtractionError, match="invalid structured output twice"):
        extract_with_llm(scanned_doc, llm)
    assert len(llm.calls) == 2   # never a third attempt


def test_too_short_transcription_counts_as_invalid(scanned_doc):
    llm = FakeLLM(as_json(strong_extraction(raw_text="hi")))
    with pytest.raises(ExtractionError, match="twice"):
        extract_with_llm(scanned_doc, llm)


def test_missing_optional_fields_use_defaults(scanned_doc):
    r = extract_with_llm(scanned_doc, FakeLLM(as_json({"raw_text": "x" * 150})))
    assert r.name is None and r.email is None and r.github_url is None and r.github_username is None
    assert r.skills == [] and r.projects == [] and r.experience == []


def test_code_fenced_json_is_tolerated(scanned_doc):
    llm = FakeLLM("```json\n" + as_json(strong_extraction()) + "\n```")
    assert extract_with_llm(scanned_doc, llm).name == "Asha Verma" and len(llm.calls) == 1


def test_decision_fields_returned_by_the_model_are_dropped(scanned_doc):
    sneaky = strong_extraction(eligible=True, score=99, rank=1, penalty=0, recommendation="hire")
    r = extract_with_llm(scanned_doc, FakeLLM(as_json(sneaky)))
    dumped = r.model_dump()
    assert not {"eligible", "score", "rank", "penalty", "recommendation"} & set(dumped)
    assert score_resume(ground_resume(r)).total < 99   # only deterministic code scores


def test_transport_failures_are_not_retried(scanned_doc):
    llm = FakeLLM(timeout_error())
    with pytest.raises(ExtractionError, match="OCR fallback request failed.*timed out"):
        extract_with_llm(scanned_doc, llm)
    assert len(llm.calls) == 1


def test_no_llm_configured_is_a_clear_candidate_error(scanned_doc):
    with pytest.raises(ExtractionError, match="OPENROUTER_API_KEY"):
        extract_with_llm(scanned_doc, None)


def test_unsupported_evidence_is_discarded_and_supported_kept(scanned_doc):
    data = strong_extraction()
    data["projects"][0]["evidence"] = ["Built a RAG pipeline using OpenAI embeddings and FAISS to rank",
                                       "Led a team of forty engineers at Google"]
    data["projects"].append({"name": "Invented", "description": "Built a thing", "technologies": [],
                             "evidence": ["Won the Turing Award"]})
    r = ground_resume(extract_with_llm(scanned_doc, FakeLLM(as_json(data))))
    assert [p.name for p in r.projects] == ["Resume Screener"]          # fabricated project removed
    assert r.projects[0].evidence == ["Built a RAG pipeline using OpenAI embeddings and FAISS to rank"]


def test_llm_extraction_enters_the_deterministic_pipeline(scanned_doc):
    r = ground_resume(extract_with_llm(scanned_doc, FakeLLM()))
    assert check_eligibility(r).eligible
    s = score_resume(r)
    assert s.ai_project_depth > 0 and s.python_backend > 0 and s.github_activity == 0
    assert score_resume(r) == s   # same extraction -> same score
