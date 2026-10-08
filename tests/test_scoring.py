from src.models import ExtractedProject, ScoreBreakdown
from src.screening import score_resume

from .factories import PLATFORM_JOB, STRONG_PROJECT, WRAPPER_PROJECT, make_resume


def full():
    return score_resume(make_resume(projects=[STRONG_PROJECT], experience=[PLATFORM_JOB]))


def test_ai_score_is_deterministic():
    # llm10 + rag6 + tools6 + orchestration6 + eval5 + data7 = 40
    assert full().ai_project_depth == 40
    assert full() == full()


def test_python_backend_score():
    # python10 + backend(FastAPI)7 + database(PostgreSQL)5 = 22 (no async / extras)
    assert full().python_backend == 22


def test_cloud_fullstack_score():
    # AWS5 + Docker5 + React5
    assert full().cloud_fullstack == 15


def test_engineering_and_github_and_total():
    s = full()
    assert s.engineering_depth == 3          # pytest, retry, logging
    assert s.github_activity == 0
    assert s.penalty == 0
    assert s.total == 40 + 22 + 15 + 3


def test_skills_list_alone_gets_little_credit():
    s = score_resume(make_resume(skills=["Python", "FastAPI", "Docker", "AWS", "PostgreSQL"],
                                 projects=[WRAPPER_PROJECT]))
    assert s.python_backend == 10   # python in project w/ verb; FastAPI etc. only in skills -> 0
    assert s.cloud_fullstack == 0


def test_framework_name_alone_earns_half_orchestration():
    p = ExtractedProject(name="X", description="Built a bot using LangChain", technologies=["LangChain"])
    notes = score_resume(make_resume(projects=[p])).notes
    assert any("orchestration framework" in n and "+3" in n for n in notes)


def test_penalty_15_for_bare_wrapper():
    assert score_resume(make_resume(projects=[WRAPPER_PROJECT])).penalty == 15


def test_penalty_10_for_single_signal():
    p = ExtractedProject(name="Q&A", description="Built a document Q&A tool with embeddings and the OpenAI API",
                         technologies=["Python"])
    assert score_resume(make_resume(projects=[p])).penalty == 10


def test_penalty_5_for_tutorial_like():
    p = ExtractedProject(
        name="Course RAG", technologies=["Python"],
        description=("Built a RAG agent following a Udemy tutorial using embeddings, FAISS and OpenAI "
                     "function calling, parsing PDF files into a searchable store"))
    assert score_resume(make_resume(projects=[p])).penalty == 5


def test_penalty_applied_once_and_total_clamped():
    s = score_resume(make_resume(projects=[WRAPPER_PROJECT, WRAPPER_PROJECT]))
    assert s.penalty == 15 and 0 <= s.total <= 100
    assert ScoreBreakdown(penalty=15).total == 0
    assert ScoreBreakdown(ai_project_depth=40, python_backend=30, cloud_fullstack=15,
                          github_activity=10, engineering_depth=5).total == 100
