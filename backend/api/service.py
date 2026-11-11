"""Build the Day 1–7 policy pipeline from the checked-in sample documents."""

from pathlib import Path
from typing import Iterable, Optional

from backend.ingestion.chunker import chunk_policy_document
from backend.ingestion.extractor import extract_policy_document
from backend.ingestion.service import prepare_policy_document
from backend.schemas.chunk import PolicyChunk


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_DOCUMENTS = (
    {
        "document_id": "doc_leave_pto_2026_v1",
        "title": "Acme Global Technologies — Paid Time Off and Leave Policy",
        "filename": "leave_policy.md",
        "policy_category": "leave",
        "version": "2.1",
        "effective_date": "2026-01-01",
    },
    {
        "document_id": "doc_attendance_workhours_2026_v1",
        "title": "Acme Global Technologies — Workplace Attendance and Working Hours Policy",
        "filename": "attendance_policy.md",
        "policy_category": "attendance",
        "version": "1.4",
        "effective_date": "2026-01-01",
    },
    {
        "document_id": "doc_benefits_comprehensive_2026_v1",
        "title": "Acme Global Technologies — Comprehensive Employee Benefits Guide",
        "filename": "employee_benefits_policy.md",
        "policy_category": "benefits",
        "version": "3.0",
        "effective_date": "2026-01-01",
    },
    {
        "document_id": "doc_conduct_ethics_2026_v1",
        "title": "Acme Global Technologies - Code of Business Conduct and Ethics",
        "filename": "code_of_conduct_policy.txt",
        "policy_category": "code_of_conduct",
        "version": "1.2",
        "effective_date": "2026-01-01",
    },
)


def load_sample_policy_chunks(
    policy_directory: Optional[Path] = None,
) -> list[PolicyChunk]:
    """Extract and chunk checked-in policies with the existing ingestion pipeline.

    The sample policies are reprocessed when the service starts so retrieval
    always uses the same validated schemas and chunker as the ingestion tests.
    """
    directory = policy_directory or (_PROJECT_ROOT / "sample-policies")
    chunks: list[PolicyChunk] = []

    for metadata in _SAMPLE_DOCUMENTS:
        policy_path = directory / metadata["filename"]
        if not policy_path.is_file():
            raise FileNotFoundError(f"Sample policy is missing: {policy_path.name}")

        document = prepare_policy_document(dict(metadata))
        extracted, _raw_chunk = extract_policy_document(policy_path, document)
        chunks.extend(chunk_policy_document(extracted, document))

    return chunks
