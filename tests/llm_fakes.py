"""Test doubles for the LLM boundary. No network, no API key."""
import json

from src.llm import LLMError
from tests.pdf_fixtures import RESUME_LINES

RAW_TEXT = "\n".join(RESUME_LINES)


def strong_extraction(**overrides) -> dict:
    """What a well-behaved model would return for RESUME_LINES (evidence copied verbatim)."""
    data = {
        "name": "Asha Verma",
        "email": "asha.verma@example.com",
        "github_url": "github.com/asha-verma",
        "skills": ["Python", "FastAPI", "LangChain"],
        "projects": [{
            "name": "Resume Screener",
            "description": ("Built a RAG pipeline using OpenAI embeddings and FAISS to rank candidates against "
                            "job descriptions. Implemented tool calling for a multi-step agent workflow with "
                            "evaluation checks."),
            "technologies": ["Python", "FastAPI", "FAISS"],
            "evidence": ["Built a RAG pipeline using OpenAI embeddings and FAISS to rank"],
        }],
        "education": ["B.Tech Computer Science, Example Institute of Technology, 2021 - 2025"],
        "experience": [{
            "role": "Software Engineer Intern", "company": "Acme Corp",
            "description": ("Developed REST endpoints in FastAPI backed by PostgreSQL and deployed them to AWS "
                            "with Docker. Wrote pytest unit tests and added retry logic for flaky vendor APIs."),
            "technologies": [],
            "evidence": ["Developed REST endpoints in FastAPI backed by PostgreSQL"],
        }],
        "raw_text": RAW_TEXT,
    }
    data.update(overrides)
    return data


def as_json(data: dict) -> str:
    return json.dumps(data)


class FakeLLM:
    """Scripted JSONVisionClient. Each response is a str (returned) or an Exception (raised).

    The last response repeats if more calls are made than responses were scripted.
    """

    def __init__(self, *responses):
        self.responses = list(responses) or [as_json(strong_extraction())]
        self.calls: list[dict] = []

    def complete_json(self, *, system, user_text, images, schema_name, schema):
        self.calls.append({"system": system, "user_text": user_text, "images": images,
                           "schema_name": schema_name, "schema": schema})
        r = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return r


def timeout_error() -> LLMError:
    return LLMError("OpenRouter request timed out after 90s")
