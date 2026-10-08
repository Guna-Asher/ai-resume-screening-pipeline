# AI Resume Screening

A small, production-minded resume screening pipeline for the Kasparro SDE Intern assignment.

It ingests PDF resumes, applies a deterministic Python + AI eligibility filter, ranks eligible candidates out of 100, enriches the result with public GitHub data, and writes an explainable JSON result.

**The LLM is only used for document extraction when normal PDF text extraction is not usable. Python makes the eligibility, scoring, penalty, and ranking decisions.**

## Quick start

```bash
docker build -t ai-resume-screening .
cp .env.example .env                  # keys inside are optional; --env-file needs the file to exist
mkdir -p resumes output               # put PDFs (or a ZIP) in ./resumes

# CLI
docker run --rm -v "$PWD/resumes:/app/resumes" -v "$PWD/output:/app/output" --env-file .env \
  ai-resume-screening python main.py --input ./resumes --output ./output/results.json

# Web UI, then open http://localhost:8000
docker run --rm -p 8000:8000 --env-file .env \
  ai-resume-screening uvicorn src.web.app:app --host 0.0.0.0 --port 8000

# Guided interactive CLI (-it is required)
docker run --rm -it -v "$PWD:/app" -v "$PWD/output:/app/output" --env-file .env ai-resume-screening
```

Run tests:

    docker run --rm ai-resume-screening pytest

### Without Docker

Python 3.10+:

    python -m venv .venv
    source .venv/bin/activate
    pip install -e '.[dev]'
    python main.py --input ./resumes --output ./output/results.json
    pytest

Running python main.py with no arguments starts the guided interactive CLI.

## What the pipeline does

1. Normalises a directory, PDF, ZIP, or Web UI upload into a list of PDFs.
2. Detects duplicates with SHA-256 and handles bad input without stopping the batch.
3. Extracts normal PDF text with pypdf and parses it deterministically.
4. Uses an OpenRouter vision fallback only when a PDF has no usable text.
5. Grounds extracted evidence against the resume text.
6. Applies the hard Python + AI/agentic eligibility filter.
7. Scores eligible candidates with the 100-point model.
8. Adds GitHub as an optional supporting signal.
9. Ranks candidates and returns ranked, rejected, and failed results in JSON.

The CLI and Web UI call the same pipeline. The Web UI does not contain separate screening logic.

## Architecture

    PDF / ZIP / directory / Web upload
                    |
                    v
             Input normalisation
             - safe ZIP extraction
             - limits and deduplication
                    |
                    v
             PDF text extraction
                    |
              usable text?
                /                     yes        no
               |          |
               v          v
        deterministic   render pages
           parser       + OpenRouter
                         /
                v        v
             evidence grounding
                    |
                    v
          Python + AI hard filter
                    |
                    v
          deterministic scoring
                    |
                    v
           GitHub enrichment
                    |
                    v
                 ranking
                    |
                    v
              JSON / Web UI

## Project structure

    main.py
    src/
      models/        Pydantic contracts
      ingestion/     input handling and PDF ingestion
      extraction/    deterministic parser and LLM fallback
      llm/           OpenRouter adapter
      screening/     eligibility, scoring, signals
      enrichment/    GitHub API client
      pipeline/      batch orchestration and output
      cli/           interactive CLI
      web/           small FastAPI UI
    tests/
    scripts/

Dependencies are kept one-way: CLI/Web -> pipeline -> ingestion/extraction/screening/enrichment.

## Eligibility

A candidate is eligible only when both conditions are true:

- Python appears as a genuine skill, project technology, or work/implementation technology.
- The resume contains meaningful AI/LLM/RAG/agentic work in an implementation context.

Examples include LLMs, RAG, embeddings/vector search, tool-calling agents, LangChain/LangGraph/LlamaIndex, evaluation pipelines, and equivalent implementations.

Skills-list phrases such as AI enthusiast, interested in GPT, or familiar with ChatGPT do not count.

Java, JavaScript, React, and Next.js do not disqualify a candidate who still satisfies the Python + AI requirement.

Rejected candidates receive explicit reasons and are not scored or sent to GitHub enrichment.

## Scoring

The assignment's 100-point baseline is:

| Category | Points |
| --- | ---: |
| AI / Agentic / RAG project depth | 40 |
| Python & backend engineering | 30 |
| Cloud / deployment / full stack | 15 |
| GitHub activity | 10 |
| Engineering depth | 5 |

The score is deterministic and evidence-backed. Signals found in project or experience entries are preferred over skills-list-only mentions, and score notes identify the source evidence.

### Shallow AI-project penalty

- 15 points: bare LLM/API wrapper with no meaningful supporting work
- 10 points: one supporting signal
- 5 points: a few signals but weak or tutorial-like evidence
- 0 points: genuine implementation depth

Final score is clamped to 0–100. Ties are broken by AI score, Python score, then source file name.

## LLM usage

Normal digital PDFs do not use an LLM.

The OpenRouter fallback is used only for PDFs that are empty, too short, or otherwise unusable as text. Pages are rendered locally and sent with a strict Pydantic-derived schema.

The model is asked for document facts only:

- candidate details
- skills
- projects
- experience
- GitHub URL
- verbatim evidence

The schema has no eligibility, score, rank, or hiring-decision fields. Extracted claims are grounded against the returned resume text before they enter the deterministic pipeline.

A readable PDF with a layout the parser cannot reliably follow is reported as failed rather than guessed or silently sent to the model.

## GitHub enrichment

GitHub is a bonus signal, never an eligibility requirement.

Eligible candidates with a public GitHub profile receive a lightweight lookup for:

- recent repository activity: 0–5 points
- relevant / maintained repositories: 0–5 points

Results are cached during a run. Missing profiles, private accounts, rate limits, timeouts, and network failures do not stop screening.

Set GITHUB_TOKEN through the environment when authenticated API access is available.

## Failure handling

Each input is isolated from the rest of the batch.

Typical outcomes:

| Situation | Result |
| --- | --- |
| Corrupt/unreadable PDF | failed + unreadable_pdf |
| Corrupt/unsafe ZIP | failed + ZIP-specific error code |
| Unparseable readable PDF | failed + unparseable_layout |
| Scanned PDF without OpenRouter key | failed + llm_not_configured |
| LLM transport/output failure | candidate failure only |
| Duplicate PDF | skipped and counted |
| GitHub failure | candidate keeps the rest of the score |
| Missing Python or AI evidence | rejected with reasons |

User-facing failures contain clean messages and stable error codes. Technical details stay in logs.

## Output

The main output is machine-readable JSON.

Ranked candidates include:

- rank and score
- score breakdown
- matched signals
- project summary
- GitHub status
- strengths and concerns
- evidence notes

Rejected and failed candidates are also returned so that the batch can be audited without silently dropping files.

## Testing and final validation

The final Docker test run passed **185 tests**.

The supplied 50-resume set produced:

- 34 ranked
- 14 rejected
- 2 failed
- 0 duplicates

The scoring rules were audited against the top candidates and regression tests were added for over-broad keyword matches.

The Web UI was exercised for PDF, multiple-PDF, ZIP, mixed uploads, drag-and-drop, duplicate handling, error states, collapsed candidate details, and JSON download.

The public unauthenticated GitHub path and rate-limit handling were tested. The live OpenRouter fallback was not run in the final environment because no API key was available. Authenticated GitHub access was also not available for the final run.

## Design Decisions

### Deterministic eligibility

Eligibility is a hard requirement, so it stays outside the LLM. A model should not be able to turn an irrelevant resume into an eligible one.

### Deterministic scoring

The same extracted resume should produce the same score every time. This also makes each ranking decision easier to review.

### LLM only where extraction needs it

Most digital resumes already contain usable text. Calling a model for every resume would add cost, latency, and nondeterminism without enough benefit.

### Fail closed

When reliable evidence is unavailable, the system reports a visible failure instead of guessing. A missing candidate is easier to investigate than a fabricated score.

### GitHub is optional

GitHub provides useful supporting evidence, but it is an external service and should never decide eligibility or stop the batch.

### Keep infrastructure small

The assignment is time-boxed. There is no database, queue, vector store, authentication layer, or frontend framework because none is needed for the core screening task.

## If I Had More Time

1. Calibrate the keyword signals and parser against a larger labelled resume set, especially multi-column layouts.
2. Add bounded concurrency for independent GitHub and LLM calls and measure the speedup.
3. Use stronger GitHub activity data and paginate beyond the first 100 repositories.
4. Cross-check LLM-extracted text against any partial deterministic extraction.

## Known limitations

This is an engineering assignment implementation, not an autonomous hiring system. The ranking is intentionally simple and explainable rather than a learned model.

Two of the supplied 50 PDFs have layouts where normal text extraction does not preserve a reliable reading order, so they fail closed instead of being scored from uncertain evidence.

