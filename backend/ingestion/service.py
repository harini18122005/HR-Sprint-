"""Service layer for policy document ingestion preparation."""

import re
from typing import Any, Dict
import uuid

from backend.ingestion.validator import PolicyMetadataValidator
from backend.schemas.document import IngestionStatus, PolicyDocument


def _generate_document_id(category: str, title: str) -> str:
    """Generate a clean, deterministic prefix document ID."""
    clean_title = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_")[:30]
    short_uuid = uuid.uuid4().hex[:8]
    return f"doc_{category}_{clean_title}_{short_uuid}"


def prepare_policy_document(raw_metadata: Dict[str, Any]) -> PolicyDocument:
    """Validate policy metadata and instantiate a validated PolicyDocument record.

    Note: This step validates and establishes the document record schema only.
    Actual document content extraction (e.g., PDF text parsing, OCR) is decoupled
    and will occur in subsequent ingestion pipeline tasks.

    Args:
        raw_metadata: Raw dictionary containing document metadata fields.

    Returns:
        PolicyDocument: Validated record with IngestionStatus.VALIDATED.

    Raises:
        ValidationError: If any required fields are missing, formats unsupported,
                         or data constraints violated.
    """
    validated = PolicyMetadataValidator.validate(raw_metadata)

    doc_id = validated["document_id"]
    if not doc_id:
        doc_id = _generate_document_id(
            validated["policy_category"].value,
            validated["title"],
        )

    return PolicyDocument(
        document_id=doc_id,
        title=validated["title"],
        filename=validated["filename"],
        policy_category=validated["policy_category"],
        file_format=validated["file_format"],
        version=validated["version"],
        effective_date=validated["effective_date"],
        ingestion_status=IngestionStatus.VALIDATED,
        metadata=validated["metadata"],
    )
