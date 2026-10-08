import re

from src.models import ExtractedExperience, ExtractedProject
from src.pipeline import screen_resume
from src.screening import build_project_summary, score_resume
from src.screening.summary import NO_EVIDENCE

from .factories import PLATFORM_JOB, STRONG_PROJECT, WRAPPER_PROJECT, make_resume


def quoted(note: str) -> str | None:
    m = re.search(r'\| "(.*)"$', note)
    return m.group(1) if m else None


def test_every_score_note_names_its_source_and_quotes_the_resume_verbatim():
    resume = make_resume(projects=[STRONG_PROJECT], experience=[PLATFORM_JOB])
    corpus = " ".join([STRONG_PROJECT.description, *STRONG_PROJECT.technologies, PLATFORM_JOB.description])
    notes = [n for n in score_resume(resume).notes if n.startswith("+")]
    assert notes
    for note in notes:
        assert " | Project: Resume RAG Agent" in note or " | Experience: Intern @ Acme" in note, note
        q = quoted(note)
        if q:
            snippet = q.strip(".").replace("title/tech list: ", "")
            assert snippet in corpus, f"quote not found in resume text: {q!r}"
    llm = next(n for n in notes if " LLM " in n)
    assert "Project: Resume RAG Agent" in llm and "OpenAI" in quoted(llm)


def test_summary_for_a_project_candidate_lists_ai_entries_first_and_is_capped():
    plain = ExtractedProject(name="Portfolio", description="Designed a static personal website.")
    resume = make_resume(projects=[plain, WRAPPER_PROJECT, STRONG_PROJECT, plain, plain])
    lines = build_project_summary(resume).splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("Project: Chatbot") and lines[1].startswith("Project: Resume RAG Agent")


def test_experience_only_candidate_gets_a_meaningful_summary_not_a_dash():
    job = ExtractedExperience(role="AI Engineer", company="Acme",
                              description="Built an LLM agent in Python. Deployed it on AWS.")
    resume = make_resume(experience=[job])
    result = screen_resume(resume)
    assert result.project_summary == "Experience: AI Engineer @ Acme - Built an LLM agent in Python"
    assert result.status.value == "ranked"


def test_no_evidence_is_stated_not_invented():
    resume = make_resume(skills=["Python"], projects=[ExtractedProject(name="Empty", description="")])
    assert build_project_summary(resume) == NO_EVIDENCE
    assert build_project_summary(make_resume()) == NO_EVIDENCE


def test_summary_text_only_contains_extracted_words():
    resume = make_resume(projects=[STRONG_PROJECT], experience=[PLATFORM_JOB])
    allowed = set(re.findall(r"\w+", " ".join([STRONG_PROJECT.name, STRONG_PROJECT.description, PLATFORM_JOB.role,
                                                PLATFORM_JOB.company, PLATFORM_JOB.description])))
    allowed |= {"Project", "Experience"}
    assert set(re.findall(r"\w+", build_project_summary(resume))) <= allowed
