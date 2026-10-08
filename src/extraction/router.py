"""Choose how to extract a document.

Usable pypdf text -> rule-based parser (never an LLM, even if the layout is unfamiliar).
Unusable text (scanned / image-only / garbled) -> render pages -> vision LLM.
"""
from src.llm import JSONVisionClient
from src.models import ExtractedResume, IngestedDocument, IngestionStatus

from .deterministic import parse_resume_text
from .llm_fallback import ExtractionError, extract_with_llm


class ResumeExtractor:
    """Callable: IngestedDocument -> ExtractedResume. Raises ExtractionError on candidate-level failure."""

    def __init__(self, llm: JSONVisionClient | None = None):
        self.llm = llm

    def __call__(self, doc: IngestedDocument) -> ExtractedResume:
        if doc.status is IngestionStatus.OK:
            return parse_resume_text(doc.source_file, doc.text)
        if doc.status is IngestionStatus.NEEDS_FALLBACK:
            return extract_with_llm(doc, self.llm)
        raise ExtractionError("internal_error", f"Document cannot be extracted (status: {doc.status.value}).")
