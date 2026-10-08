"""Hard eligibility: Python evidence AND meaningful AI/agentic evidence. No LLM, no GitHub."""
from src.models import EligibilityResult, ExtractedResume

from .signals import ELIGIBILITY_AI, SIGNALS, build_documents, python_in_skills


def check_eligibility(resume: ExtractedResume) -> EligibilityResult:
    docs = build_documents(resume)

    python_ok = python_in_skills(resume) or any("python" in d.signals for d in docs)

    ai_signals = sorted({s for d in docs for s in d.signals & ELIGIBILITY_AI})
    ai_ok = bool(ai_signals)

    reasons: list[str] = []
    if not python_ok:
        reasons.append("No Python evidence in skills, projects or experience")
    if not ai_ok:
        skills_only = any(SIGNALS[s].search(skill) for skill in resume.skills for s in ELIGIBILITY_AI)
        reasons.append(
            "AI/LLM terms appear only in the skills list, not in any project or job"
            if skills_only else
            "No LLM / RAG / agentic / AI-framework evidence in any project or job")

    return EligibilityResult(
        eligible=python_ok and ai_ok,
        has_python_evidence=python_ok,
        has_ai_evidence=ai_ok,
        matched_signals=(["python"] if python_ok else []) + ai_signals,
        rejection_reasons=reasons,
    )
