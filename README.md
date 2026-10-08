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

The final score is calculated deterministically from validated evidence (`src/screening/`).

**Credit rule.** A signal worth N points earns N when it appears in a project or job entry that also
contains an implementation verb (built, implemented, deployed...), N/2 as a bare mention, and 0 if it
only appears in the skills list (Python alone earns 3). Each piece of evidence is paid in one category only.

| Category | Components |
| --- | --- |
| AI / Agentic / RAG (40) | LLM 10, RAG/embeddings/vector 6, tools/agents 6, orchestration 6 (framework name alone: 3), evaluation 5, data/business logic 7 |
| Python & Backend (30) | Python 12, backend framework/API 8, async/concurrency 4, database (Postgres/Redis/...) 6 |
| Cloud / Deployment / Full Stack (15) | cloud 5, Docker/Kubernetes 5, React/Next.js/full-stack 5 |
| GitHub (10) | 0 until enrichment is implemented |
| Engineering Depth (5) | 1 each: testing, modularity, reliability, caching/queues, observability |

**Thin-AI-project penalty** (once per candidate, judged on the *strongest* AI project, so a weak side
project never adds to it). "Meaningful signals" = RAG, tools/agents, workflow orchestration, evaluation,
data processing, backend, database.

| Strongest AI project | Penalty |
| --- | ---: |
| bare LLM/API call, 0 meaningful signals | 15 |
| exactly 1 meaningful signal | 10 |
| 2+ signals but tutorial-like, no implementation verb, or very short description | 5 |
| genuine implementation | 0 |

`total = max(0, min(100, sum(categories) - penalty))`.

**AI eligibility** needs an AI term (LLM, RAG, agents, embeddings, LangChain/LangGraph, tool calling...)
in an *implementation context*: the same clause as a verb like "built", or in the tech list of an entry
whose description shows implementation. "AI enthusiast", "familiar with ChatGPT" or a skills-list entry do not count.

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

## Running with Docker

Docker is the primary way to run this project; nothing needs to be installed on the host.

```bash
docker build -t ai-resume-screening .

# put PDFs in ./resumes, then:
docker run --rm \
  -v "$PWD/resumes:/app/resumes" \
  -v "$PWD/output:/app/output" \
  ai-resume-screening \
  python main.py --input ./resumes --output ./output/results.json
```

Add `--env-file .env` once LLM/GitHub stages need credentials (copy `.env.example` to `.env`).

Or with Compose (one service, same mounts, `.env` optional):

```bash
docker compose run --rm app
```

Results appear in `./output/results.json`. Tests run in the container too:

```bash
docker run --rm ai-resume-screening pytest
# or: docker compose run --rm app pytest
```

The container runs as UID 1000; on Linux hosts make sure `./output` is writable by that user.

Optional local run (Python 3.10+): `python -m venv .venv && .venv/bin/pip install pydantic pypdf httpx pytest`,
then `.venv/bin/pytest`. `.venv` is git-ignored.

> **Status:** ingestion, eligibility and scoring are implemented and tested. LLM extraction and GitHub
> enrichment are not yet implemented, so the CLI currently reports every readable PDF as `failed`
> ("LLM extraction is not implemented yet"); unreadable and duplicate PDFs are already handled.

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

```bash
docker run --rm ai-resume-screening pytest
```

Tests cover eligibility (including AI false positives), deterministic scoring, the penalty ladder,
no double-counting across categories, determinism, duplicate and malformed PDFs, and batch resilience.

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
