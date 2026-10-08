from src.extraction import ground_resume
from src.models import ExtractedProject, ExtractedResume, ScreeningStatus
from src.pipeline import screen_batch

from .factories import PLATFORM_JOB, STRONG_PROJECT, WRAPPER_PROJECT, make_resume


def test_bad_resume_does_not_stop_batch_and_ranking_is_ordered():
    bad = ExtractedResume(source_file="bad.pdf")  # no text, no content
    batch = [make_resume("wrapper", projects=[WRAPPER_PROJECT]),
             bad,
             make_resume("java", skills=["Java"]),
             make_resume("strong", projects=[STRONG_PROJECT], experience=[PLATFORM_JOB])]
    results = {r.source_file: r for r in screen_batch(batch)}
    assert results["bad.pdf"].status is ScreeningStatus.FAILED and results["bad.pdf"].error
    assert results["java.pdf"].status is ScreeningStatus.REJECTED
    assert results["strong.pdf"].rank == 1 and results["wrapper.pdf"].rank == 2


def test_grounding_tolerates_pdf_whitespace_and_drops_unsupported_claims():
    raw = "Skills: Python,\nFastAPI\n• Built a RAG\nchatbot using   FAISS and OpenAI"
    r = ExtractedResume(
        source_file="x.pdf", raw_text=raw, skills=["python", "Kubernetes"],
        projects=[ExtractedProject(name="Bot", evidence=["Built a RAG chatbot using FAISS"]),
                  ExtractedProject(name="Invented", evidence=["Led a team of 40 engineers at Google"])])
    g = ground_resume(r)
    assert g.skills == ["python"] and [p.name for p in g.projects] == ["Bot"]
