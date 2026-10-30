"""Ingestion module for HR policy documents."""

from .extractor import (
    ExtractedDocument,
    ExtractionError,
    PDFDocumentExtractor,
    PolicyDocumentExtractor,
    TextDocumentExtractor,
    extract_policy_document,
    normalize_text,
)
from .service import prepare_policy_document
from .validator import PolicyMetadataValidator, ValidationError

__all__ = [
    "PolicyMetadataValidator",
    "ValidationError",
    "prepare_policy_document",
    "ExtractedDocument",
    "ExtractionError",
    "normalize_text",
    "TextDocumentExtractor",
    "PDFDocumentExtractor",
    "PolicyDocumentExtractor",
    "extract_policy_document",
]
