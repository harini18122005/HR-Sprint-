# Backend Services — HR Policy AI Assistant

This directory contains the server-side architecture, data schemas, ingestion pipeline, and query processing modules for the source-grounded HR knowledge assistant.

---

## Architecture Overview

```text
backend/
├── schemas/                # Canonical data schemas
│   ├── document.py         # PolicyDocument, PolicyCategory, IngestionStatus, DocumentFormat
│   └── chunk.py            # PolicyChunk, SourceMetadata
├── ingestion/              # Ingestion pipeline modules
│   ├── validator.py        # PolicyMetadataValidator & ValidationError
│   └── service.py          # prepare_policy_document service entrypoint
├── docs/                   # Technical specifications & documentation
│   └── ingestion_schema.md # Detailed specification of schemas, validation, and lifecycle
└── tests/                  # Unit and integration test suites
    └── test_ingestion_schema.py
```

---

## Running Tests

All unit tests rely purely on the Python standard library with no external dependencies required:

```bash
python -m unittest discover -s backend/tests
```
