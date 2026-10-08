"""Keyword signals found in project / experience text. Pure, deterministic."""
import re
from dataclasses import dataclass

from src.models import ExtractedResume


def _rx(*terms: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(terms) + r")(?![a-z0-9])", re.I)


SIGNALS: dict[str, re.Pattern[str]] = {
    "python": _rx(r"python3?"),
    # --- AI ---
    "llm": _rx(r"llms?", r"large language models?", r"chat-?gpt", r"gpt[-\s]?\w*", r"openai", r"gemini",
               r"claude", r"anthropic", r"llama[-\s]?\d*", r"mistral", r"openrouter", r"hugging\s?face",
               r"prompt engineering", r"generative ai", r"genai"),
    "rag": _rx(r"rag", r"retrieval[-\s]augmented( generation)?", r"retriev(?:al|er)s?", r"embeddings?",
               r"vector[-\s](?:search|db|database|store|index)\w*", r"faiss", r"chroma(?:db)?", r"pinecone",
               r"pgvector", r"qdrant", r"weaviate", r"milvus", r"semantic search", r"rerank\w*"),
    "tools": _rx(r"tool[-\s]calling", r"tool[-\s]use", r"function[-\s]calling", r"agents?", r"agentic",
                 r"mcp", r"model context protocol", r"multi-?agent"),
    "frameworks": _rx(r"langchain", r"langgraph", r"llama[-\s]?index", r"google adk", r"agent development kit",
                      r"adk", r"crewai", r"autogen", r"haystack", r"semantic kernel"),
    "orch_generic": _rx(r"orchestrat\w*", r"multi-?step", r"workflows?", r"state machines?", r"stateful",
                        r"state management", r"planner"),
    "eval_ai": _rx(r"llm[-\s]evaluation", r"evals?", r"evaluation (?:pipeline|harness|framework|suite)s?",
                   r"ragas", r"guardrails?", r"langsmith", r"langfuse", r"hallucination\w*",
                   r"llm[-\s]as[-\s](?:a[-\s])?judge"),
    "eval": _rx(r"evaluat\w*", r"validat\w*", r"benchmark\w*", r"evals?", r"ragas",
                r"guardrails?", r"langsmith", r"langfuse", r"hallucination\w*"),
    "data": _rx(r"data (?:processing|pipelines?|extraction|ingestion|cleaning)", r"etl", r"pars(?:e|ing|er)\w*",
                r"extract\w*", r"classif\w*", r"ranking", r"scoring", r"recommend\w*", r"analytics", r"ocr",
                r"pdfs?", r"document (?:processing|analysis)", r"summari[sz]\w*", r"business logic",
                r"knowledge base"),
    # --- Python / backend ---
    "backend": _rx(r"fastapi", r"django", r"flask", r"rest(?:ful)?(?: apis?)?", r"(?:http|web) apis?", r"backend",
                   r"back-end", r"microservices?", r"express(?:js)?", r"node(?:\.?js)?", r"spring(?: boot)?",
                   r"graphql", r"endpoints?", r"server-side"),
    "async": _rx(r"async\w*", r"asyncio", r"concurren\w*", r"parallel\w*", r"multi-?thread\w*", r"threading",
                 r"aiohttp"),
    "database": _rx(r"postgres(?:ql)?", r"redis", r"mysql", r"mongodb", r"sqlite", r"sql", r"databases?",
                    r"sqlalchemy", r"dynamodb", r"supabase", r"firebase"),
    # --- cloud / full stack ---
    "cloud": _rx(r"gcp", r"google cloud", r"aws", r"amazon web services", r"azure", r"lambda", r"ec2", r"s3",
                 r"cloud run", r"vercel", r"heroku", r"render", r"railway", r"cloud", r"deployed",
                 r"deployment"),
    "docker": _rx(r"docker\w*", r"containeri[sz]\w*", r"containers?", r"kubernetes", r"k8s"),
    "frontend": _rx(r"react(?:\.?js)?", r"next\.?js", r"vue(?:\.?js)?", r"angular", r"svelte", r"frontend",
                    r"front-end", r"full[-\s]?stack", r"tailwind", r"end-to-end"),
    # --- engineering depth ---
    # NOTE: signal vocabularies are disjoint across scoring categories so one piece of
    # evidence is never paid twice (e.g. concurrency -> backend only; queues/cache -> engineering only;
    # monitoring/logging -> engineering only; LLM eval tooling -> AI only; Kubernetes -> Docker only).
    "testing": _rx(r"pytest", r"unit tests?", r"integration tests?", r"unittest", r"test coverage", r"testing",
                   r"tests", r"ci/cd", r"github actions"),
    "modular": _rx(r"modular\w*", r"clean architecture", r"layered", r"separation of concerns",
                   r"design patterns?"),
    "reliability": _rx(r"retr(?:y|ies|ying)", r"fallbacks?", r"error handling", r"fault[-\s]toleran\w*",
                       r"graceful\w*", r"idempoten\w*", r"exception handling", r"circuit breaker", r"timeouts?"),
    "cache_queue": _rx(r"caching", r"cache", r"queues?", r"celery", r"kafka", r"rabbitmq", r"message brokers?"),
    "observability": _rx(r"logging", r"logs", r"monitoring", r"observability", r"prometheus", r"grafana",
                         r"tracing", r"sentry", r"opentelemetry"),
}

# Any one of these inside a project/job counts as meaningful AI evidence for eligibility.
ELIGIBILITY_AI = frozenset({"llm", "rag", "tools", "frameworks", "eval_ai"})

# Signals that show real work beyond a bare LLM call (used by the thin-project penalty).
MEANINGFUL = frozenset({"rag", "tools", "orch_generic", "eval", "data", "backend", "database"})

# Past, present (-s) and -ing forms. Deliberately no bare "use/used/using": "used ChatGPT" is not implementation.
IMPLEMENTATION_VERBS = _rx(
    r"built", r"builds?", r"building", r"implemented", r"implements?", r"implementing", r"developed", r"develops?",
    r"developing", r"designed", r"designs", r"designing", r"created", r"creates", r"creating", r"engineered",
    r"integrated", r"integrates", r"integrating", r"architected", r"deployed", r"deploys", r"deploying", r"wrote",
    r"automated", r"automates", r"optimi[sz]ed", r"orchestrated", r"configured", r"trained", r"fine-tuned",
    r"shipped", r"launched", r"migrated", r"added", r"containeri[sz]ed", r"reduced", r"improved", r"authored",
    r"constructed", r"leverag(?:e|es|ed|ing)", r"utili[sz](?:e|es|ed|ing)", r"employs?", r"employed")

TUTORIAL_MARKERS = _rx(r"tutorials?", r"udemy", r"coursera", r"bootcamp", r"course project",
                       r"follow(?:ed|ing) (?:a |the )?(?:tutorial|guide|along)")

THIN_DESCRIPTION_WORDS = 12

# A clause is a sentence-ish fragment. "Built dashboards; used ChatGPT for fun" must not turn the
# ChatGPT mention into AI evidence just because another clause contains "built".
_CLAUSE_SPLIT = re.compile(r"[.;!?](?:\s|$)|[\n\u2022]")


def _ai_evidence(label: str, description: str, technologies: list[str]) -> frozenset[str]:
    """AI signals that appear in an implementation context (the basis of AI eligibility).

    Counts: an AI signal in the same clause as an implementation verb ("Built a RAG pipeline with
    FAISS"), or in the entry's title / technology list when its description shows implementation.
    Does not count: "AI enthusiast", "interested in GPT", "familiar with ChatGPT", skills-list mentions.
    """
    found: set[str] = set()
    for clause in _CLAUSE_SPLIT.split(description):
        if IMPLEMENTATION_VERBS.search(clause):
            found |= {n for n in ELIGIBILITY_AI if SIGNALS[n].search(clause)}
    if IMPLEMENTATION_VERBS.search(description):
        header = " ".join([label, *technologies])
        found |= {n for n in ELIGIBILITY_AI if SIGNALS[n].search(header)}
    return frozenset(found)


@dataclass(frozen=True)
class Document:
    """One project or job entry, flattened to text plus the signals found in it."""
    label: str
    signals: frozenset[str]
    ai_evidence: frozenset[str]
    has_implementation: bool
    is_tutorial_like: bool
    description_words: int

    @property
    def is_ai(self) -> bool:
        return bool(self.ai_evidence)


def _make_document(label: str, description: str, technologies: list[str]) -> Document:
    text = " ".join([label, description, *technologies])
    return Document(
        label=label,
        signals=frozenset(name for name, rx in SIGNALS.items() if rx.search(text)),
        ai_evidence=_ai_evidence(label, description, technologies),
        has_implementation=bool(IMPLEMENTATION_VERBS.search(description)),
        is_tutorial_like=bool(TUTORIAL_MARKERS.search(text)),
        description_words=len(description.split()),
    )


def build_documents(resume: ExtractedResume) -> list[Document]:
    docs = [_make_document(p.name, p.description, p.technologies) for p in resume.projects]
    docs += [_make_document(f"{e.role} @ {e.company}".strip(" @"), e.description, e.technologies)
             for e in resume.experience]
    return docs


def python_in_skills(resume: ExtractedResume) -> bool:
    return any(SIGNALS["python"].search(s) for s in resume.skills)
