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
Resumes (PDF)
   ↓
pypdf text extraction ── usable text ──→ rule-based section parser ──┐
   │                                                                  │
   └─ scanned / garbled / no sections ─→ render pages locally         │
                                          → OpenRouter vision LLM     │
                                          → Pydantic validation ──────┤
                                                                      ↓
                                              evidence grounding against the resume text
                                                                      ↓
                                              hard eligibility → deterministic scoring
                                                                      ↓
                                              GitHub enrichment (not yet) → ranked JSON
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

**OpenRouter is used only when normal PDF text extraction is insufficient. It does not determine
eligibility, score, penalty, or rank.**

Normal digital PDFs never touch the LLM: pypdf extracts the text and a rule-based parser
(`src/extraction/deterministic.py`) splits it into skills / projects / experience / education.

The vision fallback runs when pypdf text is empty or garbled (scanned PDFs), or when text exists but no
project/experience section can be recognised. Pages are rendered locally with PyMuPDF (max 4 pages,
JPEG) and sent, together with a fixed extraction prompt, to OpenRouter `/api/v1/chat/completions` using
a strict JSON Schema generated from the `ResumeExtraction` Pydantic model. The model is asked only
*"what does the resume say?"*: it transcribes the text and lists projects, experience and skills with
verbatim evidence snippets. The schema has no eligibility, score, rank, or opinion fields.

The response is parsed and validated by Pydantic (one retry on invalid output), then every skill,
project, job and URL is checked against the transcribed text (case/whitespace/punctuation-insensitive);
unsupported items are discarded. The result enters the same deterministic eligibility and scoring code
as text-extracted resumes. All OpenRouter request details live in `src/llm/openrouter.py`.

| Variable | Meaning |
| --- | --- |
| `OPENROUTER_API_KEY` | Required only for the fallback. Without it, fallback candidates are reported as `failed`. |
| `OPENROUTER_MODEL` | Default `anthropic/claude-sonnet-4.6`; must support vision + structured outputs. |

## Failure Handling

Every failure is isolated to one candidate; the batch always finishes and writes `results.json`.

| Situation | Result |
| --- | --- |
| unreadable / malformed PDF | `failed` (ingestion error) |
| duplicate file (same content hash) | skipped, counted in `duplicates_skipped` |
| scanned PDF, no API key | `failed`: "...set OPENROUTER_API_KEY" |
| LLM timeout, HTTP error, HTTP 429 | `failed`; **not retried** |
| LLM returns invalid JSON / schema mismatch | one retry (with the validation error), then `failed` |
| no Python or no AI implementation evidence | `rejected` with reasons; no score, no rank |
| GitHub API failure (later stage) | candidate keeps their score without GitHub points |

The system fails closed: unsupported claims are discarded rather than guessed.

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

To enable the scanned-PDF fallback, copy `.env.example` to `.env`, set `OPENROUTER_API_KEY`, and add
`--env-file .env` to the `docker run` command (Compose reads `.env` automatically). The key is never
baked into the image or written to the output.

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

Optional real-API check (skipped unless a key is set; the normal tests never call OpenRouter):

```bash
docker run --rm --env-file .env ai-resume-screening python scripts/smoke_openrouter.py
```

> **Status:** ingestion, extraction (text + LLM fallback), eligibility and scoring are implemented and
> tested. GitHub enrichment is not implemented yet; the GitHub score is 0 for everyone.

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
no double-counting, determinism, duplicate / malformed / scanned PDFs, rule-based parsing, the OpenRouter
adapter and LLM extraction (retry, timeout, 429, grounding; all against fakes, no API key), and batch resilience.

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
