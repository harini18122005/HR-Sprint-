# Backend Services — HR Policy AI Assistant

This directory contains the server-side architecture, data schemas, ingestion pipeline, and query processing modules for the source-grounded HR knowledge assistant.

---

## Architecture Overview

```text
backend/
├── schemas/                    # Canonical data schemas
│   ├── document.py             # PolicyDocument, PolicyCategory, IngestionStatus, DocumentFormat
│   └── chunk.py                # PolicyChunk, SourceMetadata
├── ingestion/                  # Ingestion & extraction pipeline modules
│   ├── validator.py            # PolicyMetadataValidator & ValidationError
│   ├── service.py              # prepare_policy_document service entrypoint
│   └── extractor.py            # Text & PDF document extraction layer & normalization
├── docs/                       # Technical specifications & documentation
│   └── ingestion_schema.md     # Ingestion lifecycle, schemas, validation & extractor rules
└── tests/                      # Automated test suites
    ├── test_ingestion_schema.py   # Schema & metadata validation test suite
    └── test_document_extraction.py# Text extraction, normalization & provenance test suite
```

---

## Supported Formats

- **Markdown (`.md`)**: Fully supported via standard library (`TextDocumentExtractor`).
- **Plain Text (`.txt`)**: Fully supported via standard library (`TextDocumentExtractor`).
- **PDF (`.pdf`)**: Modular extractor (`PDFDocumentExtractor`) using `pypdf`.
- **Word Document (`.docx`)**: Planned for future milestone.

---

## Running Tests

All unit tests rely purely on the Python standard library with no external dependencies required:

```bash
# Run all unit tests
python -m unittest discover -s backend/tests -v

# Run extraction tests specifically
python -m unittest backend/tests/test_document_extraction.py -v
```
