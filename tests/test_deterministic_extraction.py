from src.extraction import ground_resume, parse_resume_text
from src.screening import check_eligibility

from .pdf_fixtures import RESUME_LINES

TEXT = "\n".join(RESUME_LINES)


def test_parses_a_normal_resume():
    r = parse_resume_text("a.pdf", TEXT)
    assert (r.name, r.email) == ("Asha Verma", "asha.verma@example.com")
    assert r.github_url == "github.com/asha-verma" and r.github_username == "asha-verma"
    assert r.skills == ["Python", "SQL", "JavaScript", "FastAPI", "LangChain", "React"]
    assert [p.name for p in r.projects] == ["Resume Screener", "Portfolio Site"]
    assert r.projects[0].technologies == ["Python", "FastAPI", "FAISS"]
    assert [(e.role, e.company) for e in r.experience] == [("Software Engineer Intern", "Acme Corp")]
    assert r.education and r.extraction_method == "text"


def test_wrapped_lines_stay_inside_their_entry():
    r = parse_resume_text("a.pdf", TEXT)
    assert "candidates against job descriptions" in r.projects[0].description
    assert len(r.projects) == 2


def test_works_without_blank_lines_between_entries():
    r = parse_resume_text("a.pdf", "\n".join(l for l in RESUME_LINES if l))
    assert [p.name for p in r.projects] == ["Resume Screener", "Portfolio Site"]
    assert len(r.experience) == 1


def test_tech_line_goes_to_technologies_not_description():
    text = "PROJECTS\nDoc Bot\nTech Stack: Python, LangChain\nBuilt a document Q&A bot.\n"
    p = parse_resume_text("a.pdf", text).projects[0]
    assert p.technologies == ["Python", "LangChain"] and "Tech Stack" not in p.description


def test_inline_skills_heading():
    assert parse_resume_text("a.pdf", "Skills: Python, SQL\nEXPERIENCE\nIntern | Co\n- Built things.").skills == ["Python", "SQL"]


def test_unrecognised_layout_yields_no_entries():
    r = parse_resume_text("a.pdf", "Jane Doe\nSelected Work\nBuilt a RAG chatbot in Python with FAISS.\n")
    assert not r.projects and not r.experience


def test_parser_output_survives_grounding_and_feeds_eligibility():
    r = ground_resume(parse_resume_text("a.pdf", TEXT))
    assert len(r.projects) == 2 and len(r.experience) == 1 and "FastAPI" in r.skills
    assert check_eligibility(r).eligible


def test_parser_is_deterministic():
    assert parse_resume_text("a.pdf", TEXT) == parse_resume_text("a.pdf", TEXT)


def test_link_labels_do_not_become_projects():
    text = ("PROJECTS\nVoice Agent | Python, FastAPI\nLive Demo\n- Built a real-time voice agent with tool calling.\n"
            "GitHub\n- Implemented appointment booking.\nNotes App\n- Built a notes app.\n")
    projects = parse_resume_text("a.pdf", text).projects
    assert [p.name for p in projects] == ["Voice Agent", "Notes App"]
    assert "voice agent" in projects[0].description and "appointment booking" in projects[0].description
