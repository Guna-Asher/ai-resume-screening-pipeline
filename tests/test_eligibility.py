from src.models import ExtractedProject
from src.pipeline import screen_resume
from src.models import ScreeningStatus
from src.screening import check_eligibility

from .factories import STRONG_PROJECT, WRAPPER_PROJECT, make_resume


def test_python_evidence_passes():
    r = check_eligibility(make_resume(skills=["Python"], projects=[WRAPPER_PROJECT]))
    assert r.has_python_evidence and r.eligible


def test_ai_evidence_passes():
    r = check_eligibility(make_resume(projects=[STRONG_PROJECT]))
    assert r.has_ai_evidence and {"llm", "rag", "tools"} <= set(r.matched_signals)


def test_missing_python_rejects():
    proj = ExtractedProject(name="Bot", description="Built a RAG chatbot with LangChain in Java",
                            technologies=["Java", "LangChain"])
    r = check_eligibility(make_resume(skills=["Java"], projects=[proj]))
    assert not r.eligible and not r.has_python_evidence
    assert any("Python" in x for x in r.rejection_reasons)


def test_missing_ai_rejects_and_skills_only_ai_is_not_enough():
    plain = ExtractedProject(name="Shop", description="Built an e-commerce API", technologies=["Python"])
    assert not check_eligibility(make_resume(projects=[plain])).has_ai_evidence
    r = check_eligibility(make_resume(skills=["Python", "LangChain", "RAG"], projects=[plain]))
    assert not r.eligible and "implementation context" in r.rejection_reasons[0]


def test_js_java_react_only_rejects():
    proj = ExtractedProject(name="Site", description="Built a React and Next.js storefront with a Java backend",
                            technologies=["JavaScript", "Java", "React", "Next.js"])
    r = check_eligibility(make_resume(skills=["JavaScript", "Java", "React"], projects=[proj]))
    assert not r.eligible and len(r.rejection_reasons) == 2


def test_other_languages_do_not_disqualify():
    proj = ExtractedProject(name="Agent", description="Built an agent in Python with a React UI",
                            technologies=["Python", "React", "JavaScript"])
    assert check_eligibility(make_resume(skills=["Python", "JavaScript", "Java"], projects=[proj])).eligible


def test_ineligible_candidate_gets_no_score_or_rank():
    res = screen_resume(make_resume(skills=["Java"]))
    assert res.status is ScreeningStatus.REJECTED and res.score is None and res.rank is None


# --- AI false positives: a bare mention is not implementation evidence -----------------------------
def _ai_eligible(description="", skills=("Python",), technologies=(), name="Item", job=False):
    from src.models import ExtractedExperience
    if job:
        e = ExtractedExperience(role=name, company="Co", description=description, technologies=list(technologies))
        return check_eligibility(make_resume(skills=skills, experience=[e]))
    p = ExtractedProject(name=name, description=description, technologies=list(technologies))
    return check_eligibility(make_resume(skills=skills, projects=[p]))


import pytest  # noqa: E402


@pytest.mark.parametrize("text", [
    "AI enthusiast",
    "Interested in GPT and large language models",
    "ChatGPT user",
    "Familiar with ChatGPT",
    "Attended an AI workshop on LLMs",
    "Built dashboards in Python; used ChatGPT for productivity",
    "Used GPT for productivity",
])
def test_ai_false_positives_are_rejected(text):
    assert not _ai_eligible(text, job=True).eligible
    assert not _ai_eligible(text).eligible


def test_generic_ai_skill_with_no_project_or_job_evidence_rejects():
    r = check_eligibility(make_resume(skills=["Python", "AI", "LLM", "ChatGPT", "Machine Learning"]))
    assert not r.eligible and not r.has_ai_evidence


@pytest.mark.parametrize("text", [
    "Built a RAG pipeline using OpenAI embeddings and FAISS.",
    "Implemented a LangGraph agent with tool calling.",
    "Developed an application using the OpenAI API.",
    "The system leverages LLM/RAG techniques to answer queries over a SQLite database.",
    "A chatbot that integrates the OpenAI API for customer support.",
    "Developing an agent in Python that uses tool calling.",
])
def test_genuine_ai_implementation_is_accepted(text):
    assert _ai_eligible(text).eligible
    assert _ai_eligible(text, job=True).eligible


def test_ai_in_tech_list_counts_only_when_description_shows_implementation():
    assert _ai_eligible("Built a document Q&A service", technologies=["Python", "LangChain"]).eligible
    assert not _ai_eligible("Interested in document Q&A", technologies=["Python", "LangChain"]).eligible
