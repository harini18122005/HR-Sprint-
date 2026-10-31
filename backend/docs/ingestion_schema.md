# Policy Ingestion & Schema Specification

This document details the data schemas, validation rules, text extraction pipeline, chunking engine, supported document formats, and ingestion lifecycle for the HR Policy AI Assistant (PeopleDesk AI).

---

## 1. Supported Document Formats & Extractors

The ingestion engine supports format-aware extraction with strict separation between standard-library text extraction and external format parsers:

| Format | Extension | Extractor | Standard Library | Notes |
| :--- | :--- | :--- | :---: | :--- |
| **Markdown** | `.md` | `TextDocumentExtractor` | Yes | Primary format for structured policies with headings (`#`, `##`). Page numbering is omitted (`page_number = None`). |
| **Plain Text** | `.txt` | `TextDocumentExtractor` | Yes | Unstructured or basic text policies. Page numbering is omitted (`page_number = None`). |
| **PDF** | `.pdf` | `PDFDocumentExtractor` | No (`pypdf`) | Multi-page documents. Isolated extractor requiring `pypdf`. Legitimate 1-based page numbers are preserved. |
| **Word Document** | `.docx` | Future Extractor | Optional | Planned for future milestone. |

---

## 2. Data Schemas

### 2.1 `PolicyDocument` (Document Metadata Schema)

Represents an ingested HR policy document in the system.

| Field | Type | Required | Description |
| :--- | :--- | :---: | :--- |
| `document_id` | `str` | Yes | Unique identifier (e.g. `doc_leave_pto_a1b2c3d4`). Auto-generated if omitted. |
| `title` | `str` | Yes | Official human-readable policy title (max 200 characters). |
| `filename` | `str` | Yes | Bare filename with supported extension (no directory paths allowed). |
| `policy_category`| `PolicyCategory` | Yes | Domain classification (`leave`, `attendance`, `benefits`, `remote_work`, `code_of_conduct`, `compensation`, `health_and_safety`, `general`). |
| `file_format` | `DocumentFormat` | Yes | Standardized format (`.pdf`, `.md`, `.txt`, `.docx`). |
| `version` | `str` | No | Version identifier (e.g. `"v2.1"`, `"2026.1"`). Max 50 characters. |
| `effective_date` | `str` | No | ISO 8601 calendar date (`YYYY-MM-DD`). |
| `ingestion_status`| `IngestionStatus`| Yes | Pipeline state (`pending`, `validated`, `processing`, `completed`, `failed`). |
| `metadata` | `dict` | No | Extensible key-value pairs (e.g., department, author, scope). |
| `created_at` | `str` | Yes | UTC ISO timestamp when the record was prepared. |

---

### 2.2 `PolicyChunk` (Text-Chunk Schema)

Represents an atomic, searchable passage of an HR policy for retrieval and answer grounding.

| Field | Type | Required | Description |
| :--- | :--- | :---: | :--- |
| `chunk_id` | `str` | Yes | Unique identifier for the chunk (e.g., `chk_pto_001`). |
| `document_id` | `str` | Yes | Parent policy document identifier (`foreign key`). |
| `chunk_text` | `str` | Yes | Verbatim extracted text passage from the policy. |
| `chunk_order` | `int` | Yes | 0-based sequential position of the chunk in the document. |
| `page_number` | `int` or `None` | No | 1-based page number where the text resides. **Strictly `None` if not available; never fabricated.** |
| `section_header`| `str` or `None` | No | Nearest preceding section heading for contextual orientation. |
| `source_metadata`| `SourceMetadata` | No | Provenance details enabling verifiable citations. |

---

### 2.3 `SourceMetadata` (Provenance Schema)

Contains the exact attributes needed by the RAG generation and citation layer to display transparent references to employees:

- **Attributes**: `document_id`, `document_title`, `filename`, `policy_category`, `version`, `effective_date`, `page_number`, `section_header`.
- **Citation Formatting (`to_citation()`)**:
  - With page number: `Nexus Corp Paid Time Off Policy (v2.0) | Section: 3.1 Accrual Rates | Page 4`
  - Without page number: `Remote Work Standards (1.0) | Section: Core Hours`
  - **No Fabrication Rule**: If `page_number` is `None`, the word "Page" is completely excluded.

---

## 3. Metadata Validation Rules

The `PolicyMetadataValidator` enforces strict data integrity before files can be scheduled for text extraction:

1. **Required Fields**: `title`, `filename`, and `policy_category` must be provided and cannot be empty or solely whitespace.
2. **Filename Security**: Filenames must be bare file basenames. Directory separators (`/`, `\`), path traversal sequences (`..`), and absolute paths are rejected with a `ValidationError`.
3. **Format Enforcement**: Extensions must match one of `.pdf`, `.md`, `.txt`, `.docx`. All other file types (e.g., `.exe`, `.xlsx`, `.png`) are rejected.
4. **Category Enforcement**: Must map to an established `PolicyCategory` enum value.
5. **Effective Date Validation**: If provided, `effective_date` must parse into a valid calendar date adhering strictly to `YYYY-MM-DD`.
6. **Length Boundaries**: `title` <= 200 characters, `version` <= 50 characters.
7. **Document ID Constraints**: If supplied, `document_id` must consist only of alphanumeric characters, hyphens, and underscores (`^[a-zA-Z0-9_\-]+$`).

---

## 4. Text Extraction Pipeline & Normalization

The extraction layer (`backend/ingestion/extractor.py`) reads documents and standardizes text content while safeguarding legal/policy semantics:

### 4.1 Normalization Principles
- **Newline Unification**: Converts `\r\n` (Windows) and `\r` (legacy Mac) into standard Unix `\n`.
- **Whitespace Sanitation**: Replaces non-breaking spaces (`\u00a0`) with standard ASCII spaces and strips trailing line spaces.
- **Paragraph Preservation**: Collapses excessive blank lines (`\n{3,}`) into clean double newlines (`\n\n`) to preserve paragraph structure without introducing artificial breaks.
- **Meaning Invariance**: Normalization never alters words, punctuation, numbers, or section headings within policy clauses.

---

## 5. Text Chunking & Overlap Engine

The chunking module (`backend/ingestion/chunker.py`) splits normalized policy text into smaller, meaningful passages with controlled overlap, preserving clause boundaries and context for downstream RAG retrieval.

### 5.1 Configuration (`ChunkingConfig`)
- `chunk_size` (default: **500 characters**): Target maximum size of each chunk.
- `chunk_overlap` (default: **100 characters**): Target character overlap between consecutive chunks.
- `min_chunk_size` (default: **50 characters**): Threshold below which trailing fragments are merged into the preceding chunk to avoid orphan snippets.

**Validation Constraints**:
- `chunk_size > 0`
- `0 <= chunk_overlap < chunk_size`
- `0 <= min_chunk_size <= chunk_size`

### 5.2 Boundary Preservation Strategy
1. **Paragraph & Heading Awareness**: Documents are parsed into logical text units. Markdown headings (`#`, `##`, `###`) and plain-text headers (`SECTION X: ...`) are recognized and tracked.
2. **Sentence Integrity**: Long paragraphs exceeding `chunk_size` are segmented at sentence boundaries (`.`, `!`, `?`) and word boundaries rather than slicing mid-word.
3. **Controlled Sliding Overlap**: When a chunk boundary is reached, an overlap window (~100 chars) is computed by finding the nearest whitespace/sentence boundary near the tail of the preceding chunk. This prefix primes the next chunk, ensuring critical clauses spanning boundaries are not lost during semantic retrieval.
4. **Section Context**: Every chunk automatically receives its active `section_header`, which is embedded into `PolicyChunk.section_header` and `SourceMetadata.section_header`.

```python
from backend.ingestion.chunker import PolicyChunker, ChunkingConfig, chunk_policy_document

chunker = PolicyChunker(ChunkingConfig(chunk_size=500, chunk_overlap=100))
chunks = chunker.chunk_document(extracted_doc, policy_doc)
```

---

## 6. Ingestion Lifecycle & Flow

```text
[Raw Metadata Payload]
         │
         ▼
[PolicyMetadataValidator] ──(Fails validation)──► Raise ValidationError
         │
         ▼ (Passes validation)
[prepare_policy_document]
         │
         ▼
[PolicyDocument Record Ready]
         │
         ▼
[PolicyDocumentExtractor.extract(path)]
         ├─► Validate existence & format (.md, .txt, .pdf)
         ├─► Decode UTF-8 / UTF-8-BOM (safe fallback)
         ├─► Safe text normalization (normalize_text)
         ▼
[ExtractedDocument Record]
         │
         ▼
[PolicyChunker.chunk_document(extracted, doc)]
         ├─► Structural paragraph and sentence parsing
         ├─► Heading & section context extraction
         ├─► Boundary-aware sliding window (~500 chars, ~100 overlap)
         ├─► Sequential chunk ordering (0, 1, 2...)
         ▼
[List[PolicyChunk]] (Ready for Indexing)
         │
         ▼ (Future Day 5 Milestone)
┌─────────────────────────────────────────────────────────────┐
│ 1. Embedding Generation & Vector Database Indexing          │
│ 2. Semantic Search & Source-Grounded LLM Retrieval          │
│ 3. API Query Serving Layer                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Running Tests

All unit tests rely purely on the Python standard library with no external dependencies:

```bash
# Run all unit tests
python -m unittest discover -s backend/tests -v

# Run text chunking tests specifically
python -m unittest backend/tests/test_text_chunking.py -v

# Run document extraction tests specifically
python -m unittest backend/tests/test_document_extraction.py -v
```
