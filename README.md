# AI Resume Screening

Screens a batch of resumes (about 50 per run): hard-rejects candidates without Python and real AI/LLM work,
scores the rest out of 100, adds public GitHub activity as a signal, and produces an explainable, ranked JSON shortlist.

> **LLM = witness, Python = judge.** OpenRouter is used only as a document extraction fallback when deterministic
> PDF text extraction is insufficient. It does not determine eligibility, score, penalty, or ranking.

## Problem

Given resumes, extract candidate information, apply a hard **Python + AI/agentic** eligibility rule, rank only eligible
candidates with the specified 100-point model, enrich with GitHub, and explain every decision. No database,
no deployment, no frontend framework and no vector store are needed; the state is the input files and the output JSON.

## Architecture

```text
 directory | .pdf | .zip | web upload ──► input normalisation ──► one list of PDFs        ingestion/inputs.py
                                              │ SHA-256 duplicate detection, safe ZIP extraction
                                              ▼
              pypdf text ── usable? ── yes ──► rule-based section parser                  extraction/deterministic.py
                                   └─ no (scanned / image-only) ─► render pages ─► OpenRouter vision ─► Pydantic
                                              ▼
              evidence grounding (drop anything not found in the resume text)            extraction/grounding.py
                                              ▼
              hard eligibility ─► deterministic score ─► GitHub points ─► rank ─► JSON   screening/, pipeline/
```

| Module | Responsibility |
| --- | --- |
| `models/` | Pydantic contracts only |
| `ingestion/` | input normalisation, hashing, pypdf text, page rendering |
| `extraction/` | text parser, LLM fallback, evidence grounding |
| `llm/` | OpenRouter adapter (the only code that knows its request format) |
| `screening/` | eligibility, scoring, penalty, GitHub points, project summary: pure functions, no I/O |
| `enrichment/` | GitHub API client |
| `pipeline/` | `run_batch`, the single entry point; ranking; JSON/TXT output; per-candidate error isolation |
| `cli/`, `web/`, `main.py` | thin front ends. **The Web UI is a thin wrapper over the same pipeline the CLI uses.** |

Dependencies point one way: CLI / Web → pipeline → ingestion / extraction / screening / enrichment. Screening never
imports the LLM, web or CLI code.

## Supported Inputs

* **PDF is required** and is the only resume format. **DOCX/TXT are not supported** (non-PDF files are ignored and listed in `ignored_files`).
* A directory of PDFs (recursive), a single PDF, a **ZIP** of PDFs (nested folders fine), or any mix. The Web UI accepts
  multiple PDFs, ZIPs, or both. Everything is normalised to one PDF list first, so the pipeline never knows where a file came from.
* Duplicates are detected by SHA-256 of the bytes, including a PDF present both directly and inside a ZIP.
* ZIPs are extracted to a temporary directory (always removed) without `extractall`: `..`, absolute and drive-letter paths are
  rejected, only `.pdf` entries are written, nested ZIPs are not unpacked, and file counts/sizes are capped (variables below).

## CLI

```bash
python main.py                          # guided interactive workflow (no arguments)
python main.py --input ./resumes        --output ./output/results.json     # directory
python main.py --input ./candidate.pdf  --output ./output/results.json     # single PDF
python main.py --input ./resumes.zip    --output ./output/results.json --text-output ./output/results.txt
```

With no arguments, a guided workflow asks for input type, path and output options, shows a configuration summary
(OpenRouter / GitHub token status), runs the pipeline, prints the JSON and offers export (copy / save JSON / save JSON + TXT).
It only collects settings and presents results. Any arguments run the scriptable mode. The JSON is the source of
truth; the TXT (`pipeline/report.py`) is only a rendering of the same result.

## Web UI

`FastAPI` + one plain HTML page (inline CSS and vanilla JavaScript; no build step, nothing stored). Drag and drop or browse PDFs/ZIPs,
review the file list, **Run Screening**, then see totals, a compact ranked table (click a row for source file, matched skills,
project summary, score notes with quoted evidence, GitHub status and concerns), rejected and failed lists, and download the
exact backend `results.json`. Routes: `GET /`, `POST /api/screen`, `GET /health`. The route only validates and saves uploads and
calls the same `run_batch` as the CLI. Resume text is rendered with `textContent` (never as HTML).

## Docker

Docker is the primary way to run this; nothing needs installing on the host. One image, non-root user, no services.

```bash
docker build -t ai-resume-screening .
cp .env.example .env        # needed for --env-file; keys are optional (see below)

# CLI (PDFs in ./resumes, results in ./output)
docker run --rm -v "$PWD/resumes:/app/resumes" -v "$PWD/output:/app/output" --env-file .env \
  ai-resume-screening python main.py --input ./resumes --output ./output/results.json

# Web UI -> http://localhost:8000
docker run --rm -p 8000:8000 --env-file .env \
  ai-resume-screening uvicorn src.web.app:app --host 0.0.0.0 --port 8000

# Tests
docker run --rm ai-resume-screening pytest

# Interactive guided mode (-it is required for terminal input)
docker run --rm -it -v "$PWD:/app" -v "$PWD/output:/app/output" --env-file .env ai-resume-screening
```

In the guided mode, type paths relative to the project folder (e.g. `./resumes.zip`). `docker compose run --rm app` runs
the CLI with the same mounts. On Linux hosts make sure `./output` is writable by UID 1000. Without Docker (Python 3.10+):
`python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'`, then the same `python main.py` / `pytest` /
`uvicorn src.web.app:app` commands.

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | none | enables the scanned-PDF fallback |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4.6` | must support vision + structured outputs |
| `GITHUB_TOKEN` | none | optional; raises the GitHub limit from 60 to 5000 requests/hour |
| `GITHUB_RECENT_DAYS` | `90` | window for "recent" GitHub activity |
| `MAX_FILES` / `MAX_PDF_MB` / `MAX_ZIP_MB` / `MAX_EXTRACTED_MB` | 200 / 20 / 100 / 300 | input limits |
| `MAX_UPLOAD_FILES` / `MAX_UPLOAD_MB` | 100 / 200 | web request limits |

## Eligibility Rules

Deterministic, applied before any scoring, independent of GitHub: **Python evidence AND meaningful AI evidence.**

* Python: in the skills list, or in any project or job text.
* AI (LLM, RAG, embeddings, vector search, LangChain/LangGraph/LlamaIndex/ADK, tool calling, agents, evaluation pipelines...) must appear in an
  *implementation context*: the same clause as a verb such as "built" / "implemented" / "leverages", or in the tech list of an entry whose
  description shows implementation. "AI enthusiast", "familiar with ChatGPT", "used GPT for productivity" or a skills-list entry do not count.
* Other languages never disqualify. Ineligible candidates get explicit reasons and **no score, no rank and no GitHub call**.

## Scoring Model

A signal worth N points earns N when it appears in a project/job entry that also contains an implementation verb, N/2 as a bare mention,
and 0 from the skills list alone (Python alone: 3). One piece of evidence is paid in one category only. Every awarded point is a note naming the
entry and quoting the resume text that earned it, e.g. `+10 LLM (implementation) | Project: Adaptive Agentic RAG | "...combining Groq Llama 3.3 for..."`.

| Category | Components |
| --- | --- |
| AI / Agentic / RAG (40) | LLM 10, RAG/embeddings/vector 6, tools/agents 6, orchestration 6 (a framework name alone: 3), evaluation 5, data/business logic 7 |
| Python & Backend (30) | Python 12, backend framework/API 8, async/concurrency 4, database 6 |
| Cloud / Deployment / Full Stack (15) | named cloud platform 5, Docker/Kubernetes 5, React/Next.js/full-stack app 5 |
| GitHub (10) | recent activity 0-5 + relevant repositories 0-5 (below) |
| Engineering Depth (5) | 1 each: testing, modularity, reliability, caching/queues, observability |

**Thin-AI-project penalty**, once per candidate and judged on the *strongest* AI project (a weak side project never adds to it):

| Strongest AI project | Penalty |
| --- | ---: |
| bare LLM/API call: no retrieval, tools, workflow, evaluation, data or backend logic | 15 |
| exactly one such signal | 10 |
| two or more, but tutorial-like, no implementation verb, or a very short description | 5 |
| genuine implementation | 0 |

`total = clamp(sum(categories) - penalty, 0, 100)`. Ranking: total, then AI score, then Python score, then file name.
The keyword signals are deliberately simple and were audited against the real dataset (see `tests/test_signal_precision.py`).

## LLM Usage

Digital PDFs never touch the LLM: pypdf text (re-read with PyMuPDF if pypdf emits one word per line) goes to a rule-based parser.
The fallback runs **only** when the text is empty, too short or garbled, i.e. scanned/image-only PDFs. A readable PDF whose layout
the parser cannot follow is reported as `failed` (`unparseable_layout`); it is never sent to the LLM.

For the fallback, pages are rendered locally with PyMuPDF (max 4, JPEG) and sent to OpenRouter's `/api/v1/chat/completions` with a strict
JSON Schema generated from the `ResumeExtraction` Pydantic model. The model is asked only *what the resume says*: a transcription plus
projects, experience and skills with verbatim evidence. The schema has no eligibility, score, rank or opinion fields (extras are dropped).
Output is validated by Pydantic (one retry on invalid output); every skill/project/job/URL is then checked against the transcribed text and
unsupported items are discarded. The result enters the same deterministic code as text-extracted resumes.

## GitHub Enrichment

An additional signal, **never an eligibility requirement**. Only eligible candidates are enriched: one public-API call per user
(`/users/{u}/repos`, first 100 repos), cached for the run. The URL comes from the resume text or from a PDF hyperlink.

* Recent activity (0-5): own, non-fork, non-archived, non-empty repos pushed within `GITHUB_RECENT_DAYS`: 1 -> 2, 2 -> 3, 3 -> 4, 4+ -> 5.
* Relevant repositories (0-5): Python repos (max 2) + AI/LLM/agent repos (max 2) + 1 if one of those was pushed in the last year. Stars are never scored.
* Missing profile, 404/private, rate limit, timeout or network error gives a status, 0 GitHub points and a recorded concern. The candidate is still ranked.

## Failure Handling

Every failure is isolated to one file or candidate; the run always finishes and writes the JSON. Failed results carry a clean `error` message and a
machine-readable `error_code`; technical detail goes to the log, never into the output or UI.

| Situation | `error_code` / result |
| --- | --- |
| unreadable or corrupt PDF | `unreadable_pdf` |
| corrupt ZIP, unsafe ZIP entry, oversize file, too many files | `corrupt_zip`, `unsafe_zip_entry`, `file_too_large`, `too_many_files` |
| readable PDF, layout not parseable | `unparseable_layout` (no LLM call) |
| scanned PDF and no API key | `llm_not_configured` |
| LLM timeout / HTTP error / 429 (not retried) | `llm_call_failed` |
| LLM invalid output after one retry | `llm_invalid_output` |
| unexpected bug | `internal_error` (generic message) |
| duplicate file | skipped, counted in `duplicates_skipped` |
| no Python or no AI implementation evidence | `rejected` with reasons, no score or rank |
| GitHub problem | candidate keeps their score without GitHub points |

## Design Decisions

1. **Deterministic eligibility, outside the LLM.** It is the hard filter; it must be reproducible, auditable and immune to prompt injection or a
   persuasive-sounding resume. A model call can vary run to run; a regex over extracted facts cannot.
2. **Deterministic scoring.** The same extracted resume always yields the same score, and each point links to quoted evidence, so a reviewer can
   check or dispute any number. Ranking then depends only on those scores.
3. **LLM only when PDF text extraction is insufficient.** Most resumes have a text layer, so an LLM adds cost, latency and nondeterminism for no gain.
   Where it is needed (scanned pages), it acts as OCR and returns facts only.
4. **Fail closed.** Unsupported claims are discarded rather than guessed, and an unparseable resume is reported as failed instead of being scored
   from a partial read. A wrong shortlist entry is worse than a visible gap.
5. **GitHub failures never reject a candidate.** GitHub is a bonus signal and an external, rate-limited service; resume quality must not
   depend on an API being up or on a profile being linked.
6. **No unnecessary infrastructure.** No database, queue, vector store, auth or frontend build: ~50 resumes run sequentially in seconds to a minute, and
   the input files plus one JSON output are the whole state.

## If I Had More Time

1. Calibrate the keyword signals and the text parser on a larger labelled resume set; multi-column PDFs (reading order scrambled) currently fail visibly.
2. Bounded concurrency for GitHub and LLM calls, with measurements.
3. Real commit activity from GitHub's events API instead of `pushed_at`, and pagination beyond 100 repos.
4. An independent check for LLM-extracted text (compare against any partial pypdf text).

## Testing

```bash
docker run --rm ai-resume-screening pytest
```

Offline and deterministic: no API key or network is needed (the LLM, OpenRouter HTTP and GitHub are faked or mocked). Coverage: eligibility
including false positives, scoring and the penalty ladder, no double-counting, evidence notes, signal precision, determinism, ingestion
(duplicates, malformed/scanned PDFs), input normalisation (zip-slip, limits), the text parser, OpenRouter adapter and LLM extraction
(retry, timeout, 429, grounding), GitHub enrichment, failure messages, the web API and the interactive CLI.

Verified outside the test suite on the supplied 50-resume dataset (50 files: 34 ranked, 14 rejected, 2 failed): counts reconcile, no leaked
text/secrets/paths, rejected/failed carry no score or rank, and the Web UI was driven end to end against the Docker image. **Not verified in
this environment:** the live OpenRouter call (no API key available) and authenticated GitHub access (no token); `scripts/smoke_openrouter.py` runs
the live check once a key is set.
