# Backend Services — PeopleDesk AI (HR Policy AI Assistant)

This directory contains the server-side architecture, data schemas, ingestion pipeline, lexical retrieval, grounded answer generation, and FastAPI integration for the HR policy assistant.

---

## Architecture Overview

```text
backend/
├── schemas/                    # Canonical data schemas
│   ├── document.py             # PolicyDocument, PolicyCategory, IngestionStatus, DocumentFormat
│   └── chunk.py                # PolicyChunk, SourceMetadata
├── ingestion/                  # Ingestion & document processing pipeline
│   ├── validator.py            # PolicyMetadataValidator & ValidationError
│   ├── service.py              # prepare_policy_document service entrypoint
│   ├── extractor.py            # Text & PDF document extraction & normalization
│   └── chunker.py              # Sentence & boundary-aware text chunking with overlap
├── retrieval/                  # Policy chunk search and ranking
│   └── retriever.py             # PolicyRetriever with pluggable ranking strategy and BM25
├── generation/                 # Source-grounded answer generation
│   ├── __init__.py              # Public answer-generation API
│   ├── answer_generator.py      # Structured answers, citations, and evidence checks
│   ├── prompts.py               # Evidence context and untrusted-policy instructions
│   └── providers.py             # Provider interface and OpenAI Responses API adapter
├── api/                          # FastAPI integration for the existing pipeline
│   ├── app.py                    # /api/chat, /api/health, CORS, and error mapping
│   └── service.py                # Loads sample policies through existing ingestion code
├── docs/                       # Technical specifications & documentation
│   ├── ingestion_schema.md     # Ingestion lifecycle, schemas, validation & chunking rules
│   ├── retrieval.md             # Lexical retrieval design, usage & limitations
│   ├── generation.md            # Grounding, citations, provider setup & limitations
│   └── api.md                    # HTTP endpoints and frontend setup
└── tests/                      # unittest suites for schemas, ingestion, retrieval, generation, and API (87 backend tests)
    ├── test_ingestion_schema.py   # Schema & metadata validation tests (10 tests)
    ├── test_document_extraction.py# Text extraction, normalization & provenance tests (15 tests)
    ├── test_text_chunking.py      # Text chunking, overlap & provenance tests (13 tests)
    ├── test_policy_retrieval.py   # Ranking, filtering & traceability tests (14 tests)
    ├── test_answer_generation.py  # Grounding, provider errors & citation tests (16 tests)
    ├── test_api.py                 # API validation, integration, CORS, and error tests
    └── test_end_to_end_evaluation.py # Full chat workflow and sample-policy evaluation
```

---

## Supported Formats

- **Markdown (`.md`)**: Fully supported via standard library (`TextDocumentExtractor`).
- **Plain Text (`.txt`)**: Fully supported via standard library (`TextDocumentExtractor`).
- **PDF (`.pdf`)**: Modular extractor (`PDFDocumentExtractor`) using `pypdf`.
- **Word Document (`.docx`)**: Planned for future milestone.

---

## Chunking Configuration Defaults

The text chunking module (`backend/ingestion/chunker.py`) uses sensible defaults optimized for source-grounded policy retrieval:

- **Target Chunk Size**: ~500 characters.
- **Chunk Overlap**: ~100 characters.
- **Minimum Chunk Size**: 50 characters (fragments below this are merged into the preceding chunk).
- **Boundary Preservation**: Paragraph and sentence terminators (`.`, `!`, `?`) are preserved to avoid breaking legal and policy clauses mid-sentence.
- **Section Tracking**: Active Markdown (`#`, `##`) and plain-text (`SECTION X:`) headings are tracked and attached to every generated `PolicyChunk`.

---

## Policy Retrieval

`backend/retrieval/` ranks existing `PolicyChunk` objects with a deterministic BM25 lexical baseline. It supports configurable `top_k`, optional category filtering from `SourceMetadata`, and returns scored results that retain the original chunk and source fields. It does not perform semantic search or generate answers. See [docs/retrieval.md](docs/retrieval.md) for the ranking details and a complete usage example.

---

## RAG Answer Generation

`backend/generation/` turns retrieved chunks into short, cited answers. Every generated claim must include an exact quote from a retrieved chunk; the service validates chunk IDs and quotes and builds citations from the original source metadata. It abstains when there are no results or the provider reports insufficient evidence. Live generation uses the official OpenAI Python SDK and Responses API; tests use mocks and make no API calls. See [docs/generation.md](docs/generation.md) for setup, behavior, and limitations.

Install the provider dependency with `python -m pip install -r requirements.txt`. Set `OPENAI_API_KEY` in the environment to enable live generation. `OPENAI_MODEL` optionally overrides the default model. `.env.example` contains placeholder configuration only; never commit a real key.

---

## Frontend and Backend API

`backend/api/` exposes the existing pipeline through FastAPI. `GET /api/health` reports service and provider configuration. `POST /api/chat` validates a question, retrieves from the sample policies using `PolicyRetriever`, and passes those actual results to `AnswerGenerator`. Responses include the answer or abstention, status, and citations with source filename, document ID, chunk ID, section, exact quote, and page number only when available.

If `OPENAI_API_KEY` is missing, chat requests return HTTP 503 with an explicit `not_configured` status; the API never substitutes mock policy answers. Provider errors return HTTP 502. The Day 7 static frontend calls the API and renders loading, answers, citations, abstention, and errors. It reads the browser-visible backend origin from `PEOPLEDESK_API_BASE_URL` when `python frontend/build_config.py` generates `docs/api-config.js`. See [docs/api.md](docs/api.md) and [the frontend README](../frontend/README.md) for setup and the full request flow.

Install dependencies with `python -m pip install -r requirements.txt`, then run from the repository root:

```bash
python -m uvicorn backend.api.app:app --reload --host 127.0.0.1 --port 8000
```

Set `FRONTEND_ORIGINS` to the exact comma-separated browser origins allowed by CORS. The default permits `http://localhost:4173` and `http://127.0.0.1:4173`. This milestone does not deploy the backend.

---

## Running Tests

Tests use `unittest` and mocked providers, so the test suite makes no live API calls:

```bash
# Run all unit tests
python -m unittest discover -s backend/tests -v

# Run text chunking tests specifically
python -m unittest backend/tests/test_text_chunking.py -v

# Run document extraction tests specifically
python -m unittest backend/tests/test_document_extraction.py -v

# Run schema validation tests specifically
python -m unittest backend/tests/test_ingestion_schema.py -v

# Run policy retrieval tests specifically
python -m unittest backend.tests.test_policy_retrieval -v

# Run answer generation tests specifically
python -m unittest backend.tests.test_answer_generation -v

# Run API integration tests
python -m unittest backend.tests.test_api -v

# End-to-end workflow and sample-policy retrieval evaluation
python -m unittest backend.tests.test_end_to_end_evaluation -v

# Run static frontend interaction and config checks
node --test frontend/tests/chat.test.cjs
python -m unittest frontend.tests.test_build_config -v
```

See [Testing and Evaluation](docs/testing_evaluation.md) for the workflow coverage, failure cases, limitations, and interpretation of mocked provider results.
