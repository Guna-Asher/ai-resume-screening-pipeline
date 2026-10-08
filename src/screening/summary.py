"""Short, evidence-based project summary. Built only from extracted entries; nothing is invented."""
import re

from src.models import ExtractedResume

from .signals import _CLAUSE_SPLIT, Document, build_documents

MAX_ENTRIES = 3
MAX_CHARS = 140
NO_EVIDENCE = "No project or experience entries with a description were extracted from this resume."


def _first_clause(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    clause = _CLAUSE_SPLIT.split(text)[0].strip() if text else ""
    return clause if len(clause) <= MAX_CHARS else clause[:MAX_CHARS].rsplit(" ", 1)[0] + "..."


def _line(doc: Document) -> str:
    return f"{doc.kind}: {doc.label}" + (f" - {_first_clause(doc.description)}" if doc.description.strip() else "")


def build_project_summary(resume: ExtractedResume) -> str:
    """Up to 3 entries, AI-relevant ones first, then projects before jobs, in resume order."""
    docs = [d for d in build_documents(resume) if d.description.strip()]
    if not docs:
        return NO_EVIDENCE
    ranked = sorted(docs, key=lambda d: (not d.is_ai, d.kind != "Project"))   # stable sort keeps resume order
    return "\n".join(_line(d) for d in ranked[:MAX_ENTRIES])
