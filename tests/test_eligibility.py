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
    assert not r.eligible and "only in the skills list" in r.rejection_reasons[0]


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
