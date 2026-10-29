# Policy Ingestion & Schema Specification

This document details the data schemas, validation rules, supported document formats, and ingestion lifecycle for the HR Policy AI Assistant.

---

## 1. Supported Document Formats

The ingestion module supports the following file extensions (case-insensitive):

| Format | Extension | Notes |
| :--- | :--- | :--- |
| **PDF** | `.pdf` | Multi-page documents with extractable page boundaries (`page_number`). |
| **Markdown** | `.md` | Plain text structured with headers (`#`, `##`). Has no inherent page numbering (`page_number = None`). |
| **Plain Text** | `.txt` | Unstructured or basic text policies (`page_number = None`). |
| **Word Document** | `.docx` | Formatted documents. Page numbering depends on renderer/extractor capability. |

---

## 2. Data Schemas

### 2.1 `PolicyDocument` (Document Metadata Schema)

Represents an ingested HR policy document in the system.

| Field | Type | Required | Description |
| :--- | :--- | :---: | :--- |
| `document_id` | `str` | Yes | Unique identifier (e.g. `doc_leave_pto_a1b2c3d4`). Auto-generated if omitted. |
| `title` | `str` | Yes | Official human-readable policy title (max 200 characters). |
| `filename` | `str` | Yes | Bare filename with supported extension (no directory paths allowed). |
| `policy_category`| `PolicyCategory` | Yes | Domain classification (`leave`, `benefits`, `remote_work`, `code_of_conduct`, `compensation`, `health_and_safety`, `general`). |
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

## 4. Ingestion Lifecycle & Flow

```text
[Raw Metadata Payload]
         │
         ▼
[PolicyMetadataValidator] ──(Fails validation)──► Raise ValidationError (informative field error)
         │
         ▼ (Passes validation)
[prepare_policy_document]
         │
         ├─► Resolve or generate document_id
         ├─► Set status to IngestionStatus.VALIDATED
         ▼
[PolicyDocument Record Ready]
         │
         ▼ (Future Pipeline Tasks)
┌─────────────────────────────────────────────────────────────┐
│ 1. Text & Layout Extraction (PDF, MD, DOCX parsers)         │
│ 2. Semantic & Structural Chunking (PolicyChunk generation)  │
│ 3. Embedding Generation & Vector Indexing                   │
│ 4. Grounded RAG Query Serving                               │
└─────────────────────────────────────────────────────────────┘
```

> **Separation of Concerns**: Metadata validation is strictly decoupled from heavy text extraction and OCR. This guarantees that malformed requests, unsupported formats, or security violations are rejected instantly with zero compute overhead.
