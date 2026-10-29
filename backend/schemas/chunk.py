"""Chunk schema for source-grounded policy passages."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class SourceMetadata:
    """Detailed source tracking metadata embedded in every chunk.

    Used by the RAG generation pipeline to cite authoritative policy passages
    without hallucinating facts, sections, or page numbers.
    """

    document_id: str
    document_title: str
    filename: str
    policy_category: str
    version: Optional[str] = None
    effective_date: Optional[str] = None
    page_number: Optional[int] = None
    section_header: Optional[str] = None

    def to_citation(self) -> str:
        """Construct a formatted source citation string.

        Guarantees that page numbers and section headers are only included
        when legitimately present. Never fabricates missing page numbers.
        """
        parts = [self.document_title]

        if self.version:
            parts[0] += f" ({self.version})"

        if self.section_header:
            parts.append(f"Section: {self.section_header}")

        # Page numbers are only included if legitimately provided; never fabricated.
        if self.page_number is not None:
            parts.append(f"Page {self.page_number}")

        return " | ".join(parts)


@dataclass
class PolicyChunk:
    """Schema representing an extracted, indexable passage of an HR policy.

    Attributes:
        chunk_id: Unique string identifier for this passage.
        document_id: Identifier of the parent PolicyDocument.
        chunk_text: Extracted verbatim text of the policy passage.
        chunk_order: 0-indexed position of this chunk within the document sequence.
        page_number: 1-indexed page number where the text originates (optional).
                     Must remain None for formats without page boundaries (e.g., Markdown).
        section_header: Closest preceding section or header for contextual grounding, optional.
        source_metadata: Complete provenance information linking chunk back to source policy.
    """

    chunk_id: str
    document_id: str
    chunk_text: str
    chunk_order: int
    page_number: Optional[int] = None
    section_header: Optional[str] = None
    source_metadata: Optional[SourceMetadata] = None

    def __post_init__(self) -> None:
        """Validate chunk schema constraints."""
        if not self.chunk_id or not self.chunk_id.strip():
            raise ValueError("chunk_id must be a non-empty string.")
        if not self.document_id or not self.document_id.strip():
            raise ValueError("document_id must be a non-empty string.")
        if not self.chunk_text or not self.chunk_text.strip():
            raise ValueError("chunk_text must be a non-empty string.")
        if self.chunk_order < 0:
            raise ValueError("chunk_order must be a non-negative integer.")
        if self.page_number is not None and self.page_number < 1:
            raise ValueError("page_number must be a positive 1-based integer when provided.")

    def get_citation_reference(self) -> str:
        """Return the formatted citation reference for this chunk."""
        if self.source_metadata:
            return self.source_metadata.to_citation()
        base = f"Doc ID: {self.document_id}"
        if self.page_number is not None:
            base += f" | Page {self.page_number}"
        return base

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk schema to serializable dictionary."""
        data = asdict(self)
        if self.source_metadata:
            data["source_metadata"] = asdict(self.source_metadata)
        return data
