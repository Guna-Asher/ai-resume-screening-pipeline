"""Choose how to extract a document: free deterministic text parsing first, vision LLM only if needed."""
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
            resume = parse_resume_text(doc.source_file, doc.text)
            if resume.projects or resume.experience:
                return resume  # normal digital PDF: no LLM call
            reason = "text extracted but no project/experience section recognised"
        elif doc.status is IngestionStatus.NEEDS_FALLBACK:
            reason = "too little usable text (scanned or image-only PDF)"
        else:
            raise ExtractionError(f"document not extractable: {doc.status.value}")
        try:
            return extract_with_llm(doc, self.llm)
        except ExtractionError as e:
            raise ExtractionError(f"{reason}; {e}") from None
