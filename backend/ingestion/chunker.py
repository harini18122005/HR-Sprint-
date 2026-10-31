"""Text chunking module for HR Policy AI Assistant (PeopleDesk AI).

Splits extracted HR policy documents into smaller, meaningful passages with
controlled overlap while preserving sentence and paragraph boundaries, sequential
ordering, unique identifiers, and source metadata provenance.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.ingestion.extractor import ExtractedDocument
from backend.schemas.chunk import PolicyChunk, SourceMetadata
from backend.schemas.document import PolicyDocument


@dataclass(frozen=True)
class ChunkingConfig:
    """Configuration parameters for text chunking.

    Attributes:
        chunk_size: Target maximum character length for each chunk (default ~500 chars).
        chunk_overlap: Approximate character overlap between consecutive chunks (default ~100 chars).
        min_chunk_size: Minimum characters required for a trailing standalone chunk (default 50 chars).
    """

    chunk_size: int = 500
    chunk_overlap: int = 100
    min_chunk_size: int = 50

    def __post_init__(self) -> None:
        """Validate chunking configuration constraints."""
        for name, value in (
            ("chunk_size", self.chunk_size),
            ("chunk_overlap", self.chunk_overlap),
            ("min_chunk_size", self.min_chunk_size),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer, got {value!r}.")

        if self.chunk_size <= 0:
            raise ValueError(
                f"chunk_size must be a positive integer, got {self.chunk_size}."
            )
        if self.chunk_overlap < 0:
            raise ValueError(
                f"chunk_overlap must be a non-negative integer, got {self.chunk_overlap}."
            )
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be strictly less than "
                f"chunk_size ({self.chunk_size})."
            )
        if self.min_chunk_size < 0:
            raise ValueError(
                f"min_chunk_size must be non-negative, got {self.min_chunk_size}."
            )
        if self.min_chunk_size > self.chunk_size:
            raise ValueError(
                f"min_chunk_size ({self.min_chunk_size}) cannot exceed chunk_size ({self.chunk_size})."
            )


# Patterns to detect headings in Markdown and plain text policies
_MARKDOWN_HEADER_PATTERN = re.compile(r"^#{1,6}\s+(.+)$")
_SECTION_HEADER_PATTERN = re.compile(
    r"^(?:SECTION\s+\d+|ARTICLE\s+[IVXLCDM\d]+|\d+\.\s+[A-Z])[:\s].+$",
    re.IGNORECASE,
)


def _detect_heading(line: str) -> Optional[str]:
    """Detect if a single line represents a policy section heading."""
    stripped = line.strip()
    if not stripped:
        return None

    # Check Markdown headers (# Header, ## 2. Section)
    md_match = _MARKDOWN_HEADER_PATTERN.match(stripped)
    if md_match:
        return md_match.group(1).strip()

    # Check plain text headers (SECTION 1: ..., 1. PURPOSE)
    if _SECTION_HEADER_PATTERN.match(stripped) and len(stripped) < 150:
        return stripped

    return None


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences while respecting common sentence terminators."""
    if not text:
        return []
    raw_sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    return sentences if sentences else [text.strip()]


def _split_large_paragraph(paragraph: str, max_size: int) -> List[str]:
    """Break a long paragraph into smaller units respecting sentence or word boundaries."""
    sentences = _split_into_sentences(paragraph)
    units: List[str] = []

    for sentence in sentences:
        if len(sentence) <= max_size:
            units.append(sentence)
        else:
            words = sentence.split()
            current_words: List[str] = []
            current_len = 0
            for w in words:
                w_len = len(w)
                additional = w_len + (1 if current_words else 0)
                if current_len + additional <= max_size:
                    current_words.append(w)
                    current_len += additional
                else:
                    if current_words:
                        units.append(" ".join(current_words))
                    current_words = [w]
                    current_len = w_len
            if current_words:
                units.append(" ".join(current_words))

    return [u for u in units if u.strip()]


@dataclass
class _TextUnit:
    """Internal atomic unit of text paired with contextual heading."""

    text: str
    section_header: Optional[str] = None
    page_number: Optional[int] = None


class PolicyChunker:
    """Splits policy text into overlapping chunks preserving sentence and clause boundaries."""

    def __init__(self, config: Optional[ChunkingConfig] = None):
        """Initialize chunker with configuration settings.

        Args:
            config: ChunkingConfig specifying chunk_size, chunk_overlap, and min_chunk_size.
        """
        self.config = config or ChunkingConfig()

    def _prepare_text_units(
        self,
        raw_text: str,
        default_page_number: Optional[int] = None,
    ) -> List[_TextUnit]:
        """Parse raw text into manageable text units while tracking active section headings."""
        lines = raw_text.split("\n")
        units: List[_TextUnit] = []
        current_heading: Optional[str] = None
        current_paragraph_lines: List[str] = []

        def flush_paragraph() -> None:
            if not current_paragraph_lines:
                return
            paragraph_text = " ".join(current_paragraph_lines).strip()
            current_paragraph_lines.clear()
            if not paragraph_text:
                return

            if len(paragraph_text) <= self.config.chunk_size:
                units.append(_TextUnit(
                    text=paragraph_text,
                    section_header=current_heading,
                    page_number=default_page_number,
                ))
            else:
                sub_parts = _split_large_paragraph(
                    paragraph_text,
                    self.config.chunk_size,
                )
                for part in sub_parts:
                    units.append(_TextUnit(
                        text=part,
                        section_header=current_heading,
                        page_number=default_page_number,
                    ))

        for line in lines:
            stripped = line.strip()
            if not stripped:
                flush_paragraph()
                continue

            detected = _detect_heading(stripped)
            if detected:
                flush_paragraph()
                current_heading = detected
                units.append(_TextUnit(
                    text=stripped,
                    section_header=current_heading,
                    page_number=default_page_number,
                ))
            else:
                current_paragraph_lines.append(stripped)

        flush_paragraph()
        return units

    def _compute_overlap_prefix(
        self,
        accumulated_text: str,
        overlap_size: int,
    ) -> str:
        """Extract a clean, boundary-respecting overlap prefix from the tail of accumulated text."""
        if not accumulated_text or overlap_size <= 0:
            return ""

        if len(accumulated_text) <= overlap_size:
            return accumulated_text

        # Take trailing overlap window
        window = accumulated_text[-overlap_size:]

        # Find first whitespace boundary in the window to avoid cutting mid-word
        first_space = window.find(" ")
        if first_space != -1 and first_space < len(window) - 10:
            return window[first_space + 1:].strip()

        return window.strip()

    def chunk_text(
        self,
        text: str,
        document_id: str,
        source_metadata: Optional[SourceMetadata] = None,
        page_number: Optional[int] = None,
    ) -> List[PolicyChunk]:
        """Split arbitrary policy text into PolicyChunk objects with controlled overlap.

        Args:
            text: Policy text to split.
            document_id: Unique identifier of the source policy document.
            source_metadata: Provenance metadata to attach to every chunk.
            page_number: Optional legitimate 1-based page number (None for Markdown/TXT).

        Returns:
            List[PolicyChunk]: Sequence of PolicyChunk records with sequential chunk_order.
        """
        if not text or not text.strip():
            return []

        resolved_page_number = (
            page_number
            if page_number is not None
            else source_metadata.page_number
            if source_metadata is not None
            else None
        )
        clean_text = text.strip()
        units = self._prepare_text_units(
            clean_text,
            default_page_number=resolved_page_number,
        )

        if not units:
            return []

        chunks: List[PolicyChunk] = []
        chunk_order = 0

        # Edge case: If total text fits within chunk_size, return a single chunk
        if len(clean_text) <= self.config.chunk_size:
            primary_header = units[0].section_header if units else None
            meta = None
            if source_metadata:
                meta = SourceMetadata(
                    document_id=source_metadata.document_id,
                    document_title=source_metadata.document_title,
                    filename=source_metadata.filename,
                    policy_category=source_metadata.policy_category,
                    version=source_metadata.version,
                    effective_date=source_metadata.effective_date,
                    page_number=resolved_page_number,
                    section_header=primary_header or source_metadata.section_header,
                )

            chunk_id = f"chk_{document_id}_{chunk_order:03d}"
            chunks.append(PolicyChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                chunk_text=clean_text,
                chunk_order=chunk_order,
                page_number=resolved_page_number,
                section_header=primary_header,
                source_metadata=meta,
            ))
            return chunks

        def create_chunk(chunk_content: str, header: Optional[str]) -> PolicyChunk:
            nonlocal chunk_order
            cid = f"chk_{document_id}_{chunk_order:03d}"
            meta = None
            if source_metadata:
                meta = SourceMetadata(
                    document_id=source_metadata.document_id,
                    document_title=source_metadata.document_title,
                    filename=source_metadata.filename,
                    policy_category=source_metadata.policy_category,
                    version=source_metadata.version,
                    effective_date=source_metadata.effective_date,
                    page_number=resolved_page_number,
                    section_header=header or source_metadata.section_header,
                )
            chk = PolicyChunk(
                chunk_id=cid,
                document_id=document_id,
                chunk_text=chunk_content.strip(),
                chunk_order=chunk_order,
                page_number=resolved_page_number,
                section_header=header,
                source_metadata=meta,
            )
            chunk_order += 1
            return chk

        current_chunk_text = ""
        current_section_header: Optional[str] = None

        for unit in units:
            if not current_chunk_text:
                current_chunk_text = unit.text
                if unit.section_header:
                    current_section_header = unit.section_header
                continue

            candidate = f"{current_chunk_text}\n\n{unit.text}"
            if len(candidate) <= self.config.chunk_size:
                current_chunk_text = candidate
                if unit.section_header:
                    current_section_header = unit.section_header
            else:
                # Emit current_chunk_text
                chunks.append(create_chunk(current_chunk_text, current_section_header))

                # Calculate overlap prefix from previous chunk text
                overlap_prefix = self._compute_overlap_prefix(
                    current_chunk_text,
                    self.config.chunk_overlap,
                )

                if overlap_prefix and (len(overlap_prefix) + len(unit.text) + 2 <= self.config.chunk_size):
                    current_chunk_text = f"{overlap_prefix}\n\n{unit.text}"
                else:
                    current_chunk_text = unit.text

                if unit.section_header:
                    current_section_header = unit.section_header

        # Flush trailing content
        if current_chunk_text:
            if len(current_chunk_text.strip()) >= self.config.min_chunk_size or not chunks:
                chunks.append(create_chunk(current_chunk_text, current_section_header))
            elif chunks:
                # Merge small trailing fragment with last chunk
                last_chunk = chunks[-1]
                merged_text = f"{last_chunk.chunk_text}\n\n{current_chunk_text.strip()}"
                chunks[-1] = PolicyChunk(
                    chunk_id=last_chunk.chunk_id,
                    document_id=last_chunk.document_id,
                    chunk_text=merged_text,
                    chunk_order=last_chunk.chunk_order,
                    page_number=last_chunk.page_number,
                    section_header=last_chunk.section_header,
                    source_metadata=last_chunk.source_metadata,
                )

        return chunks

    def chunk_document(
        self,
        extracted: ExtractedDocument,
        document: PolicyDocument,
    ) -> List[PolicyChunk]:
        """Split an ExtractedDocument into PolicyChunks using an authoritative PolicyDocument.

        Args:
            extracted: Result of document extraction containing full text and format.
            document: Validated PolicyDocument providing document ID and metadata.

        Returns:
            List[PolicyChunk]: Generated chunks with complete provenance and sequential order.
        """
        # Only attach page numbers when the extractor retained page-bounded text.
        # A page count alone cannot identify which page a passage came from.
        page_texts = extracted.pages or [(None, extracted.text)]
        chunks: List[PolicyChunk] = []

        for source_page_number, page_text in page_texts:
            base_meta = SourceMetadata(
                document_id=document.document_id,
                document_title=document.title,
                filename=document.filename,
                policy_category=document.policy_category.value,
                version=document.version,
                effective_date=document.effective_date,
                page_number=source_page_number,
                section_header=None,
            )
            page_chunks = self.chunk_text(
                text=page_text,
                document_id=document.document_id,
                source_metadata=base_meta,
                page_number=source_page_number,
            )

            for page_chunk in page_chunks:
                order = len(chunks)
                chunks.append(PolicyChunk(
                    chunk_id=f"chk_{document.document_id}_{order:03d}",
                    document_id=document.document_id,
                    chunk_text=page_chunk.chunk_text,
                    chunk_order=order,
                    page_number=source_page_number,
                    section_header=page_chunk.section_header,
                    source_metadata=page_chunk.source_metadata,
                ))

        return chunks


def chunk_policy_document(
    extracted: ExtractedDocument,
    document: PolicyDocument,
    config: Optional[ChunkingConfig] = None,
) -> List[PolicyChunk]:
    """Convenience helper to chunk an ExtractedDocument with optional custom configuration.

    Args:
        extracted: ExtractedDocument containing normalized text.
        document: Validated PolicyDocument schema.
        config: Optional ChunkingConfig override.

    Returns:
        List[PolicyChunk]: List of sequential policy chunks.
    """
    chunker = PolicyChunker(config=config)
    return chunker.chunk_document(extracted, document)
