from src.models import ExtractedExperience, ExtractedProject, ExtractedResume

STRONG_PROJECT = ExtractedProject(
    name="Resume RAG Agent",
    description=("Built a multi-agent RAG workflow in Python using LangGraph, FAISS embeddings and OpenAI "
                 "function calling; implemented an evaluation harness and PDF parsing behind FastAPI "
                 "and PostgreSQL"),
    technologies=["Python", "FastAPI", "PostgreSQL"],
)

PLATFORM_JOB = ExtractedExperience(
    role="Intern", company="Acme",
    description=("Deployed services on AWS with Docker and a React dashboard; wrote pytest unit tests, "
                 "added retry logic and structured logging."),
)

WRAPPER_PROJECT = ExtractedProject(
    name="Chatbot", description="Built a chatbot that calls the OpenAI API", technologies=["Python", "OpenAI"])


def make_resume(name="cand", skills=("Python",), projects=(), experience=()) -> ExtractedResume:
    return ExtractedResume(source_file=f"{name}.pdf", name=name, skills=list(skills),
                           projects=list(projects), experience=list(experience),
                           raw_text=f"resume text of {name}")
