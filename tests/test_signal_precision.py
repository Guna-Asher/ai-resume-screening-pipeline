"""Regression tests from auditing the real 50-resume dataset: phrases that used to earn points from an
over-broad keyword (left), and genuine phrasings that must keep earning them (right)."""
import pytest

from src.models import ExtractedProject
from src.screening.signals import build_documents

from .factories import make_resume


def signals(description: str) -> frozenset[str]:
    p = ExtractedProject(name="X", description=description)
    return build_documents(make_resume(projects=[p]))[0].signals


NOT_EARNED = [
    ("cloud", "Integrated Azure OpenAI and OpenAI APIs for document understanding."),
    ("cloud", "Built a platform using FastAPI and Azure/OpenAI LLM APIs."),
    ("cloud", "Built a platform using FastAPI and Azure-OpenAI."),
    ("cloud", "Developed and deployed an end-to-end automated ingestion pipeline."),
    ("cloud", "Designed and deployed a fully offline Android chatbot."),
    ("frontend", "Collaborated closely with frontend engineers and product managers."),
    ("frontend", "Built a copilot wiring frontend to backend to agent."),
    ("frontend", "Built an end-to-end RAG pipeline for insurance policy documents."),
    ("orch_generic", "Built services to power AI-driven enterprise HRMS workflows."),
    ("orch_generic", "Socket.io powering real-time swipe, match, and chat workflows."),
    ("data", "Built branded PDF proposal generation and scheduling."),
    ("data", "Supporting data-driven product decisions with scalable analytics."),
    ("backend", "Created a pure Python blockchain with a JSON-RPC node interface."),
    ("backend", "Shipped a feature in Spring 2024 to express interest."),
    ("testing", "Built lessons, concept checks and hidden tests for learners."),
    ("testing", "Delivered buyer discovery that was 60% faster in MVP testing."),
    ("testing", "Automated execution every 5 minutes using GitHub Actions."),
    ("observability", "Built a graph-based agent to automate interaction logging and follow-ups."),
    ("llm", "Deployed the final CNN classifier on Hugging Face for image classification."),
]

EARNED = [
    ("cloud", "Deployed the API on AWS."),
    ("cloud", "Worked with Azure PowerShell and Azure/OpenAI."),
    ("cloud", "Hosted the service on Azure App Service."),
    ("cloud", "Deployed across Vercel, Render, and LiveKit."),
    ("frontend", "Built a React dashboard."),
    ("frontend", "Developed a full-stack application."),
    ("frontend", "Built an end-to-end conversational application on EC2."),
    ("orch_generic", "Built LangChain-based multi-step agent workflows."),
    ("orch_generic", "Built an LLM-driven workflow engine."),
    ("orch_generic", "Built a multi-agent RAG workflow."),
    ("data", "Built PDF parsing and metadata extraction."),
    ("backend", "Built a Node.js backend with Express.js."),
    ("backend", "Developed REST APIs in FastAPI."),
    ("testing", "Wrote pytest unit tests."),
    ("testing", "Added automated testing and integration tests."),
    ("observability", "Added structured logging and OpenTelemetry tracing."),
    ("observability", "Set up monitoring with Grafana."),
    ("llm", "Built a chatbot with the OpenAI API."),
]


@pytest.mark.parametrize("signal,text", NOT_EARNED)
def test_over_broad_keyword_no_longer_earns_the_signal(signal, text):
    assert signal not in signals(text)


@pytest.mark.parametrize("signal,text", EARNED)
def test_genuine_evidence_still_earns_the_signal(signal, text):
    assert signal in signals(text)
