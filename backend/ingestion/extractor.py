"""Text and document extraction module for HR Policy AI Assistant.

Provides robust, format-aware text extraction for supported policy documents.
Uses the Python standard library for text formats (.md, .txt) and preserves
source provenance without fabricating missing metadata (such as page numbers).
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.schemas.chunk import PolicyChunk, SourceMetadata
from backend.schemas.document import DocumentFormat, PolicyDocument


class ExtractionError(Exception):
    """Raised when document extraction fails due to formatting, I/O, or encoding errors.

    Attributes:
        message: Human-readable error description.
        filename: Optional name of the file that encountered the error.
        cause: Optional underlying exception that caused the extraction failure.
    """

    def __init__(
        self,
        message: str,
        filename: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.filename = filename
        self.cause = cause

    def __str__(self) -> str:
        if self.filename:
            return f"Extraction error in '{self.filename}': {self.message}"
        return f"Extraction error: {self.message}"


@dataclass
class ExtractedDocument:
    """Standardized representation of extracted document text and provenance.

    Attributes:
        text: Normalized full text content extracted from the document.
        filename: Name of the source file (basename).
        file_format: Standardized format enum of the source document.
        metadata: Extraction metrics and file statistics (e.g. word count, character count).
        page_count: Number of pages if legitimately supported by the format; None for text/markdown.
        pages: Optional list of (page_number, page_text) tuples for page-bounded formats.
    """

    text: str
    filename: str
    file_format: DocumentFormat
    metadata: Dict[str, Any] = field(default_factory=dict)
    page_count: Optional[int] = None
    pages: Optional[List[Tuple[int, str]]] = None

    def to_raw_chunk(
        self,
        document: PolicyDocument,
        chunk_id: Optional[str] = None,
    ) -> PolicyChunk:
        """Create a single document-level PolicyChunk connecting text to document provenance.

        Note: Granular chunk splitting and sliding-window overlaps are implemented in Day 4.
        This provides a valid raw chunk representation adhering to existing schemas.

        Args:
            document: Validated PolicyDocument providing authoritative metadata.
            chunk_id: Optional explicit chunk ID; generated deterministically if omitted.

        Returns:
            PolicyChunk: Validated chunk record with attached SourceMetadata.
        """
        resolved_chunk_id = chunk_id or f"chk_{document.document_id}_raw"

        # Explicitly preserve page number only if legitimately available; never fabricate
        source_page_number = 1 if self.page_count is not None and self.page_count > 0 else None

        source_meta = SourceMetadata(
            document_id=document.document_id,
            document_title=document.title,
            filename=document.filename,
            policy_category=document.policy_category.value,
            version=document.version,
            effective_date=document.effective_date,
            page_number=source_page_number,
            section_header=None,
        )

        return PolicyChunk(
            chunk_id=resolved_chunk_id,
            document_id=document.document_id,
            chunk_text=self.text,
            chunk_order=0,
            page_number=source_page_number,
            section_header=None,
            source_metadata=source_meta,
        )


def normalize_text(raw_text: str) -> str:
    """Safely normalize document text without altering policy clause meaning.

    Operations performed:
    1. Unify newline representations (CRLF and CR to LF).
    2. Replace non-breaking spaces (\u00a0) with standard ASCII spaces.
    3. Strip trailing whitespace from each line.
    4. Collapse excessive consecutive blank lines (> 2 newlines) into standard double newlines.
    5. Strip leading and trailing outer whitespace.

    Args:
        raw_text: Unprocessed string content.

    Returns:
        str: Cleaned, normalized text content.
    """
    if not raw_text:
        return ""

    # Unify line breaks
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # Replace non-breaking spaces
    text = text.replace("\u00a0", " ")

    # Strip trailing whitespace on each line while preserving indentation/bullet structures
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Collapse runs of 3 or more newlines into 2 (paragraph break)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


class TextDocumentExtractor:
    """Extractor for text-based policy documents (.md, .txt) using standard library."""

    SUPPORTED_EXTENSIONS = {DocumentFormat.MD.value, DocumentFormat.TXT.value}

    @classmethod
    def can_extract(cls, file_format: Union[str, DocumentFormat]) -> bool:
        """Check if format is supported by this extractor."""
        ext = file_format.value if isinstance(file_format, DocumentFormat) else file_format.lower()
        return ext in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def extract(cls, file_path: Union[str, Path]) -> ExtractedDocument:
        """Extract and normalize text from a Markdown or plain text document.

        Args:
            file_path: Path to the target file.

        Returns:
            ExtractedDocument: Normalized text and metadata.

        Raises:
            ExtractionError: If the file does not exist, is unreadable, has invalid encoding,
                             or is empty.
        """
        path = Path(file_path)

        if not path.exists():
            raise ExtractionError(
                f"File not found: '{path.name}'.",
                filename=path.name,
            )

        if not path.is_file():
            raise ExtractionError(
                f"Path '{path.name}' is a directory, not a valid document file.",
                filename=path.name,
            )

        ext = path.suffix.lower()
        if ext not in cls.SUPPORTED_EXTENSIONS:
            raise ExtractionError(
                f"Unsupported format '{ext}'. TextDocumentExtractor supports: {sorted(cls.SUPPORTED_EXTENSIONS)}",
                filename=path.name,
            )

        # Read file with UTF-8 / UTF-8-sig encoding handling
        raw_bytes = path.read_bytes()
        if len(raw_bytes) == 0:
            raise ExtractionError(
                f"Document '{path.name}' is empty (0 bytes).",
                filename=path.name,
            )

        decoded_text: Optional[str] = None
        encoding_used: Optional[str] = None

        # Try UTF-8 with BOM first, then standard UTF-8
        for enc in ("utf-8-sig", "utf-8"):
            try:
                decoded_text = raw_bytes.decode(enc)
                encoding_used = enc
                break
            except UnicodeDecodeError:
                continue

        if decoded_text is None:
            raise ExtractionError(
                f"Unable to decode '{path.name}'. File must be valid UTF-8 text.",
                filename=path.name,
            )

        # Normalize text
        normalized = normalize_text(decoded_text)
        if not normalized:
            raise ExtractionError(
                f"Document '{path.name}' contains only whitespace after normalization.",
                filename=path.name,
            )

        # Compute document statistics
        words = normalized.split()
        lines = normalized.split("\n")
        metadata = {
            "character_count": len(normalized),
            "word_count": len(words),
            "line_count": len(lines),
            "encoding": encoding_used,
            "file_size_bytes": len(raw_bytes),
        }

        # Page numbering is strictly None for text/markdown formats; never fabricated
        return ExtractedDocument(
            text=normalized,
            filename=path.name,
            file_format=DocumentFormat(ext),
            metadata=metadata,
            page_count=None,
            pages=None,
        )


class PDFDocumentExtractor:
    """Extractor for PDF policy documents, isolated from standard-library text extraction.

    Uses 'pypdf' if installed. If 'pypdf' is not present, raises an informative
    ExtractionError explaining the dependency requirement.
    """

    SUPPORTED_EXTENSIONS = {DocumentFormat.PDF.value}

    @classmethod
    def can_extract(cls, file_format: Union[str, DocumentFormat]) -> bool:
        """Check if format is PDF."""
        ext = file_format.value if isinstance(file_format, DocumentFormat) else file_format.lower()
        return ext in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def extract(cls, file_path: Union[str, Path]) -> ExtractedDocument:
        """Extract text from a PDF document.

        Args:
            file_path: Path to the target PDF file.

        Returns:
            ExtractedDocument: Extracted text with legitimate page counts.

        Raises:
            ExtractionError: If pypdf is missing, the file is unreadable, or contains no text.
        """
        path = Path(file_path)

        if not path.exists():
            raise ExtractionError(f"File not found: '{path.name}'.", filename=path.name)

        if not path.is_file():
            raise ExtractionError(
                f"Path '{path.name}' is a directory, not a valid document file.",
                filename=path.name,
            )

        try:
            import pypdf  # type: ignore[import-untyped]
        except ImportError as err:
            raise ExtractionError(
                "PDF extraction requires the 'pypdf' dependency. "
                "Install it using 'pip install pypdf' or use supported text formats (.md, .txt).",
                filename=path.name,
                cause=err,
            )

        try:
            reader = pypdf.PdfReader(str(path))
            pages_text: List[Tuple[int, str]] = []

            for idx, page in enumerate(reader.pages):
                extracted = page.extract_text() or ""
                normalized_page = normalize_text(extracted)
                if normalized_page:
                    pages_text.append((idx + 1, normalized_page))

            full_text = "\n\n".join(t for _, t in pages_text)
            full_text = normalize_text(full_text)

            if not full_text:
                raise ExtractionError(
                    f"PDF document '{path.name}' contains no readable text.",
                    filename=path.name,
                )

            metadata = {
                "character_count": len(full_text),
                "word_count": len(full_text.split()),
                "total_pages": len(reader.pages),
            }

            return ExtractedDocument(
                text=full_text,
                filename=path.name,
                file_format=DocumentFormat.PDF,
                metadata=metadata,
                page_count=len(reader.pages),
                pages=pages_text,
            )
        except Exception as e:
            if isinstance(e, ExtractionError):
                raise
            raise ExtractionError(
                f"Failed to extract PDF '{path.name}': {str(e)}",
                filename=path.name,
                cause=e,
            )


class PolicyDocumentExtractor:
    """Unified dispatcher for document text extraction across supported formats."""

    @classmethod
    def extract(cls, file_path: Union[str, Path]) -> ExtractedDocument:
        """Extract text content from any supported policy document file.

        Args:
            file_path: Path to the document.

        Returns:
            ExtractedDocument: Standardized extracted text and metadata.

        Raises:
            ExtractionError: On unsupported formats, missing files, or extraction errors.
        """
        path = Path(file_path)

        if not path.exists():
            raise ExtractionError(
                f"File not found: '{path.name}'.",
                filename=path.name,
            )

        if path.is_dir():
            raise ExtractionError(
                f"Path '{path.name}' is a directory, not a valid document file.",
                filename=path.name,
            )

        ext = path.suffix.lower()

        if not ext:
            raise ExtractionError(
                f"File '{path.name}' lacks a file extension. Supported formats: {[f.value for f in DocumentFormat]}.",
                filename=path.name,
            )

        if not DocumentFormat.has_extension(ext):
            raise ExtractionError(
                f"Unsupported document format '{ext}' for file '{path.name}'. Supported formats: {[f.value for f in DocumentFormat]}.",
                filename=path.name,
            )

        doc_format = DocumentFormat(ext)

        if TextDocumentExtractor.can_extract(doc_format):
            return TextDocumentExtractor.extract(path)
        elif PDFDocumentExtractor.can_extract(doc_format):
            return PDFDocumentExtractor.extract(path)
        else:
            raise ExtractionError(
                f"No suitable extractor available for format '{ext}'.",
                filename=path.name,
            )


def extract_policy_document(
    file_path: Union[str, Path],
    document: Optional[PolicyDocument] = None,
) -> Tuple[ExtractedDocument, Optional[PolicyChunk]]:
    """Convenience function to extract a document and optionally create a raw PolicyChunk.

    Args:
        file_path: Path to the document file.
        document: Optional validated PolicyDocument to connect with chunk output.

    Returns:
        Tuple[ExtractedDocument, Optional[PolicyChunk]]: Extracted text record and attached chunk.
    """
    extracted = PolicyDocumentExtractor.extract(file_path)
    chunk = extracted.to_raw_chunk(document) if document else None
    return extracted, chunk
