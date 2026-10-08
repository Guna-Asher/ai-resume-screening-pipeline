# AI Resume Screening & Ranking

Screen a batch of resumes (about 50 in one run), reject candidates who fail a hard Python + AI rule, score the
rest out of 100, enrich with public GitHub activity, and produce an explainable ranked JSON shortlist.

> **LLM = witness, Python = judge.** OpenRouter is used only as a document extraction fallback when
> deterministic PDF text extraction is insufficient. It does not determine eligibility, score, penalty, or ranking.

## Architecture

```text
 dir | .pdf | .zip | web upload ──► input normalisation ──► one list of PDFs   (src/ingestion/inputs.py)
                                          │ SHA-256 duplicate detection, safe ZIP extraction
                                          ▼
                      pypdf text ── usable? ── yes ──► rule-based section parser      (src/extraction/deterministic.py)
                                          └─── no (scanned / garbled) ──► render pages ► OpenRouter vision ► Pydantic
                                          ▼
                      evidence grounding (drop anything not found in the resume text)
                                          ▼
                      hard eligibility ─► deterministic score ─► GitHub enrichment ─► rank ─► JSON   (src/screening, src/pipeline)
```

| Module | Responsibility |
| --- | --- |
| `models/` | Pydantic contracts only |
| `ingestion/` | input normalisation, hashing, pypdf, page rendering |
| `extraction/` | text parser, LLM fallback, evidence grounding |
| `llm/` | OpenRouter adapter (the only place that knows its request format) |
| `screening/` | eligibility, scoring, penalty, GitHub points. Pure functions, no I/O |
| `enrichment/` | GitHub API client |
| `pipeline/` | `run_batch` (the one entry point), ranking, JSON/TXT output, per-candidate error isolation |
| `web/` | FastAPI route + one HTML page. **A thin wrapper around the same pipeline the CLI uses.** |

## Supported Inputs

A directory of PDFs (recursive), a single PDF, a ZIP of PDFs (nested folders fine), or any mix. The Web UI accepts
multiple PDFs, ZIPs, or both. Everything is normalised to one PDF list before the pipeline starts, so the rest of
the code never knows where a file came from. A PDF present both directly and inside a ZIP is caught as a duplicate (SHA-256).

ZIPs are extracted to a temporary directory (removed afterwards) without `extractall`: entries with `..`, absolute
or drive-letter paths are rejected, only `.pdf` entries are written, nested ZIPs are not unpacked, and file count and
sizes are capped (see below). Non-PDF files are ignored and listed in `ignored_files`.

## CLI Usage

```bash
python main.py --input ./resumes        --output ./output/results.json     # directory
python main.py --input ./candidate.pdf  --output ./output/results.json     # single PDF
python main.py --input ./resumes.zip    --output ./output/results.json --text-output ./output/results.txt
```

The JSON is the source of truth. `--text-output` is only a rendering of the same result (`pipeline/report.py`).

## Web UI

`FastAPI` + one plain HTML page (no build step, no database, nothing stored). Drag & drop or browse PDFs/ZIPs, review
the file list, click **Run Screening**; see counts, a ranked table with per-candidate details (matched skills, score
notes, GitHub, concerns), rejected and failed lists, and download the exact backend `results.json`.
Routes: `GET /`, `POST /api/screen`, `GET /health`. The route only validates and saves uploads, then calls the same
`run_batch` as the CLI. All page text from resumes is inserted with `textContent` (never as HTML).

## Docker

Docker is the primary way to run this; nothing needs installing on the host. One image, non-root user.

```bash
docker build -t ai-resume-screening .
cp .env.example .env        # optional: OPENROUTER_API_KEY, GITHUB_TOKEN

# CLI
docker run --rm -v "$PWD/resumes:/app/resumes" -v "$PWD/output:/app/output" --env-file .env \
  ai-resume-screening python main.py --input ./resumes --output ./output/results.json

# Web UI -> http://localhost:8000
docker run --rm -p 8000:8000 --env-file .env \
  ai-resume-screening uvicorn src.web.app:app --host 0.0.0.0 --port 8000

# Tests
docker run --rm ai-resume-screening pytest
```

`docker compose run --rm app` runs the CLI with the same mounts (`.env` optional). On Linux hosts make sure
`./output` is writable by UID 1000. Real-API check for the fallback (skipped without a key):
`docker run --rm --env-file .env ai-resume-screening python scripts/smoke_openrouter.py`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | none | enables the scanned-PDF fallback |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4.6` | must support vision + structured outputs |
| `GITHUB_TOKEN` | none | optional; raises the GitHub rate limit (60/h unauthenticated) |
| `GITHUB_RECENT_DAYS` | `90` | window for "recent" GitHub activity |
| `MAX_FILES` / `MAX_PDF_MB` / `MAX_ZIP_MB` / `MAX_EXTRACTED_MB` | 200 / 20 / 100 / 300 | input limits |
| `MAX_UPLOAD_FILES` / `MAX_UPLOAD_MB` | 100 / 200 | web request limits |

## Eligibility

Deterministic, evaluated before any scoring and independent of GitHub: **Python evidence AND meaningful AI evidence.**

* Python: listed in skills, or present in any project or job text.
* AI (LLM, RAG, embeddings, vector search, LangChain/LangGraph/LlamaIndex/ADK, tool calling, agents, evaluation
  pipelines...) must appear in an *implementation context*: the same clause as a verb like "built"/"implemented", or in
  the tech list of an entry whose description shows implementation. "AI enthusiast", "familiar with ChatGPT" or a
  skills-list entry do not count.
* Other languages never disqualify. Ineligible candidates get explicit reasons, **no score, no rank, no GitHub call**.

## Scoring

A signal worth N points earns N when it appears in a project/job entry that also contains an implementation verb, N/2 as
a bare mention, and 0 from the skills list alone (Python alone: 3). Each piece of evidence is paid in one category only.

| Category | Components |
| --- | --- |
| AI / Agentic / RAG (40) | LLM 10, RAG/embeddings/vector 6, tools/agents 6, orchestration 6 (framework name alone: 3), evaluation 5, data/business logic 7 |
| Python & Backend (30) | Python 12, backend framework/API 8, async/concurrency 4, database 6 |
| Cloud / Deployment / Full Stack (15) | cloud 5, Docker/Kubernetes 5, React/Next.js/full-stack 5 |
| GitHub (10) | recent activity 0-5 + relevant repositories 0-5 (see below) |
| Engineering Depth (5) | 1 each: testing, modularity, reliability, caching/queues, observability |

**Thin-AI-project penalty**, once per candidate and judged on the *strongest* AI project (a weak side project never adds to it):

| Strongest AI project | Penalty |
| --- | ---: |
| bare LLM/API call, no retrieval, tools, workflow, evaluation, data or backend logic | 15 |
| exactly one such signal | 10 |
| two or more, but tutorial-like, no implementation verb, or a very short description | 5 |
| genuine implementation | 0 |

`total = clamp(sum(categories) - penalty, 0, 100)`. Ranking: total, then AI score, then Python score, then file name.
Every awarded point is listed in `score.notes`.

## LLM Usage

**OpenRouter is used only as a document extraction fallback when deterministic PDF text extraction is insufficient.
It does not determine eligibility, score, penalty, or ranking.**

Digital PDFs never touch the LLM: pypdf text (re-read with PyMuPDF if pypdf returns one word per line, a quirk seen in real PDFs) goes to a rule-based parser. The fallback runs only when pypdf text is empty,
too short, or garbled (scanned / image-only PDFs). An unfamiliar layout in a *readable* PDF does **not** trigger it: that
candidate is reported as `failed` ("unrecognised layout"), a visible parser limitation.

For the fallback, pages are rendered locally with PyMuPDF (max 4, JPEG) and sent to `/api/v1/chat/completions` with a strict
JSON Schema generated from the `ResumeExtraction` Pydantic model. The model is only asked *what the resume says*:
a transcription plus projects, experience and skills with verbatim evidence snippets. The schema has no eligibility, score,
rank or opinion fields (extras are dropped). Output is validated by Pydantic (one retry on invalid output), then every
skill/project/job/URL is checked against the transcribed text (case/whitespace/punctuation-insensitive); unsupported items
are discarded.

## GitHub Enrichment

Only eligible candidates are enriched, via one public-API call per user (`/users/{u}/repos`, first 100 repos), cached for
the run. The URL comes from the resume text, or from a PDF hyperlink when the visible text just says "GitHub".

* Recent activity (0-5): own, non-fork, non-archived, non-empty repos pushed within `GITHUB_RECENT_DAYS`: 1 -> 2, 2 -> 3, 3 -> 4, 4+ -> 5.
* Relevant repositories (0-5): Python repos (max 2) + AI/LLM/agent/RAG repos (max 2) + 1 if one of those was pushed in the last year.
* Stars are recorded but never scored.

Unauthenticated GitHub allows 60 requests/hour, roughly one 50-resume run, so set `GITHUB_TOKEN` for repeated runs.
Missing profile, 404/private, rate limit, timeout and network errors produce a status (`not_provided`, `not_found`,
`rate_limited`, `error`), 0 GitHub points and a concern; the candidate is still ranked.

## Failure Handling

Every failure is isolated to one candidate or file; the run always finishes and writes the JSON.

| Situation | Result |
| --- | --- |
| unreadable PDF, corrupt ZIP, unsafe ZIP entry, oversize file | `failed` with a safe message |
| duplicate file (same SHA-256) | skipped, counted in `duplicates_skipped` |
| non-PDF file | ignored, listed in `ignored_files` |
| scanned PDF and no API key | `failed`: "...set OPENROUTER_API_KEY" |
| LLM timeout / HTTP error / 429 | `failed`, not retried |
| LLM invalid JSON or schema mismatch | one retry with the error, then `failed` |
| readable PDF, unrecognised layout | `failed` (no LLM call) |
| no Python or no AI implementation evidence | `rejected` with reasons; no score or rank |
| GitHub problem | candidate keeps their score without GitHub points |

Fails closed: unsupported claims are discarded, never guessed. API keys are read from the environment only and never
logged or written to output; web errors never include stack traces.

## Design Decisions

* Hard rules and arithmetic live in plain Python (`src/screening`); the LLM only turns pixels into text and structure.
* Keyword/clause signals are crude but explainable: every point traces to a note, and tests pin the behaviour.
* One `run_batch` for CLI and web, so there is one place where results are produced.
* No database, queue, vector store or frontend build; state is the input files and the output JSON.
* Sequential processing: simple and predictable at ~50 resumes (LLM calls only for scanned files).

## If I Had More Time

1. Calibrate keyword signals and the layout parser on a larger real resume set (multi-column layouts parse poorly).
2. Bounded concurrency for LLM/GitHub calls, with measurements.
3. Use GitHub's events or commit APIs for real activity instead of `pushed_at`, and page beyond 100 repos.
4. Independent grounding for LLM output (compare against partial pypdf text) and OCR-quality checks.
5. DOCX/TXT inputs, a persisted run history, and a TXT download in the web UI.
