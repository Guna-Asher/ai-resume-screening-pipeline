# AI Resume Screening Pipeline

A small production-minded resume screening pipeline built for the SDE Intern AI Resume Screening assignment.

## Problem

Process a batch of approximately 50 resumes and:

1. Extract candidate information from each resume.
2. Apply hard Python + AI/agentic eligibility filters.
3. Score eligible candidates using the provided 100-point model.
4. Enrich results with public GitHub activity.
5. Produce an explainable ranked shortlist in JSON.

The system is designed around:

> **LLM as witness, code as judge.**

LLMs are used for semantic extraction and project-quality assessment. Deterministic Python code handles eligibility rules, score calculation, validation, ranking, and pipeline decisions.

## Pipeline

```text
Resumes
   ↓
PDF extraction
   ↓
Structured candidate extraction
   ↓
Hard eligibility filter
   ↓
AI/project quality assessment
   ↓
Deterministic scoring
   ↓
GitHub enrichment
   ↓
Ranked JSON output
```

## Eligibility

A candidate must have both:

* Genuine Python evidence
* Meaningful AI / LLM / RAG / agentic evidence

Eligibility is rule-based. A strong-looking resume cannot override a failed hard requirement.

## Scoring

Eligible candidates are scored out of 100:

| Category                         | Weight |
| -------------------------------- | -----: |
| AI / Agentic / RAG Project Depth |     40 |
| Python & Backend Engineering     |     30 |
| Cloud / Deployment / Full Stack  |     15 |
| GitHub Activity                  |     10 |
| Engineering Depth                |      5 |

The final score is calculated deterministically from validated evidence.

## LLM Usage

The LLM is used for semantic tasks such as:

* extracting candidate/project information
* identifying implementation evidence
* assessing project depth
* producing short explanations

LLM output is required to follow a structured schema and is validated before being used by the pipeline.

The LLM does not directly decide the final score or eligibility.

## Failure Handling

The batch should continue when an individual resume, LLM call, or GitHub enrichment request fails.

Examples:

* unreadable resume → candidate-level failure
* invalid LLM response → retry/reject safely
* GitHub API failure → continue without GitHub enrichment
* missing GitHub profile → candidate remains eligible
* missing required evidence → candidate is rejected

The system fails closed rather than inventing unsupported results.

## Running

```bash
python main.py --input ./resumes --output ./output/results.json
```

## Environment

Copy `.env.example` to `.env` and provide the required API configuration.

Never commit real credentials.

## Output

The generated JSON contains:

* candidate name
* eligibility status
* rejection reasons
* matched skills
* project summary
* score breakdown
* GitHub enrichment
* strengths and concerns
* final rank

A batch summary is also included.

## Tests

Run:

```bash
pytest
```

Tests focus on the most important screening behavior, including eligibility, scoring, malformed input, model failures, and batch resilience.

## Design Decisions

The system intentionally keeps hard business rules outside the LLM.

The model acts as a semantic witness and provides structured evidence. Deterministic Python code validates the evidence, applies eligibility rules, calculates scores, applies project-quality penalties, and produces the final ranking.

The implementation favors explainability and reliability over complex scoring mathematics or unnecessary infrastructure.

## If I Had More Time

Potential improvements:

1. Add DOCX/TXT parsing.
2. Add bounded asynchronous processing with measured performance improvement.
3. Add caching for repeated GitHub/LLM lookups.
4. Add a small terminal or HTML report for easier result inspection.
