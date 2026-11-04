# Backend Services — PeopleDesk AI (HR Policy AI Assistant)

This directory contains the server-side architecture, data schemas, ingestion pipeline, document text extraction, and chunking modules for the source-grounded HR knowledge assistant.

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
├── docs/                       # Technical specifications & documentation
│   ├── ingestion_schema.md     # Ingestion lifecycle, schemas, validation & chunking rules
│   └── retrieval.md             # Lexical retrieval design, usage & limitations
└── tests/                      # Automated test suites (52 unit tests)
    ├── test_ingestion_schema.py   # Schema & metadata validation tests (10 tests)
    ├── test_document_extraction.py# Text extraction, normalization & provenance tests (15 tests)
    ├── test_text_chunking.py      # Text chunking, overlap & provenance tests (13 tests)
    └── test_policy_retrieval.py   # Ranking, filtering & traceability tests (14 tests)
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

## Running Tests

All unit tests rely purely on the Python standard library with zero external dependencies:

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
```
