"""Validation logic for HR policy document metadata."""

from datetime import datetime
import os
from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple

from backend.schemas.document import DocumentFormat, PolicyCategory


class ValidationError(ValueError):
    """Exception raised when document metadata fails validation rules.

    Attributes:
        message: Human-readable explanation of why validation failed.
        field: Name of the metadata field that caused the error (if applicable).
    """

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.field = field

    def __str__(self) -> str:
        if self.field:
            return f"Validation error on field '{self.field}': {self.message}"
        return f"Validation error: {self.message}"


class PolicyMetadataValidator:
    """Validates raw policy metadata prior to ingestion and indexing.

    Ensures that documents conform to required schemas, supported file formats,
    and security constraints (e.g., preventing path traversal).
    """

    MAX_TITLE_LENGTH = 200
    MAX_VERSION_LENGTH = 50
    VALID_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")

    @classmethod
    def validate_title(cls, title: Any) -> str:
        """Validate document title."""
        if title is None:
            raise ValidationError("Missing required field 'title'.", field="title")
        if not isinstance(title, str) or not title.strip():
            raise ValidationError("Field 'title' must be a non-empty string.", field="title")
        trimmed = title.strip()
        if len(trimmed) > cls.MAX_TITLE_LENGTH:
            raise ValidationError(
                f"Field 'title' exceeds maximum length of {cls.MAX_TITLE_LENGTH} characters.",
                field="title",
            )
        return trimmed

    @classmethod
    def validate_filename(cls, filename: Any) -> Tuple[str, DocumentFormat]:
        """Validate filename safety and supported extension."""
        if filename is None:
            raise ValidationError("Missing required field 'filename'.", field="filename")
        if not isinstance(filename, str) or not filename.strip():
            raise ValidationError("Field 'filename' must be a non-empty string.", field="filename")

        trimmed = filename.strip()

        # Check for path traversal or directory separators
        if "/" in trimmed or "\\" in trimmed or ".." in trimmed or os.path.basename(trimmed) != trimmed:
            raise ValidationError(
                "Field 'filename' must be a bare filename without directory paths or traversal sequences.",
                field="filename",
            )

        ext = Path(trimmed).suffix.lower()
        if not ext:
            raise ValidationError(
                f"Field 'filename' is missing a file extension. Supported formats: {[f.value for f in DocumentFormat]}.",
                field="filename",
            )

        if not DocumentFormat.has_extension(ext):
            raise ValidationError(
                f"Unsupported file format '{ext}'. Supported formats: {[f.value for f in DocumentFormat]}.",
                field="filename",
            )

        return trimmed, DocumentFormat(ext)

    @classmethod
    def validate_category(cls, category: Any) -> PolicyCategory:
        """Validate policy category against recognized HR domains."""
        if category is None:
            raise ValidationError("Missing required field 'policy_category'.", field="policy_category")
        if not isinstance(category, (str, PolicyCategory)):
            raise ValidationError("Field 'policy_category' must be a string.", field="policy_category")

        if isinstance(category, PolicyCategory):
            return category

        raw_str = category.strip().lower()
        try:
            return PolicyCategory(raw_str)
        except ValueError:
            valid_categories = [c.value for c in PolicyCategory]
            raise ValidationError(
                f"Invalid policy category '{category}'. Allowed categories: {valid_categories}.",
                field="policy_category",
            )

    @classmethod
    def validate_effective_date(cls, date_str: Any) -> Optional[str]:
        """Validate optional ISO 8601 date string (YYYY-MM-DD)."""
        if date_str is None:
            return None
        if not isinstance(date_str, str):
            raise ValidationError("Field 'effective_date' must be a string in YYYY-MM-DD format.", field="effective_date")

        trimmed = date_str.strip()
        if not trimmed:
            return None

        try:
            parsed = datetime.strptime(trimmed, "%Y-%m-%d").date()
            return parsed.isoformat()
        except ValueError:
            raise ValidationError(
                f"Invalid 'effective_date' format '{date_str}'. Expected valid ISO calendar date YYYY-MM-DD.",
                field="effective_date",
            )

    @classmethod
    def validate_version(cls, version: Any) -> Optional[str]:
        """Validate optional version string."""
        if version is None:
            return None
        if not isinstance(version, (str, int, float)):
            raise ValidationError("Field 'version' must be a string or number.", field="version")

        trimmed = str(version).strip()
        if not trimmed:
            return None
        if len(trimmed) > cls.MAX_VERSION_LENGTH:
            raise ValidationError(
                f"Field 'version' exceeds maximum length of {cls.MAX_VERSION_LENGTH} characters.",
                field="version",
            )
        return trimmed

    @classmethod
    def validate_document_id(cls, document_id: Any) -> Optional[str]:
        """Validate optional pre-assigned document identifier."""
        if document_id is None:
            return None
        if not isinstance(document_id, str):
            raise ValidationError("Field 'document_id' must be a string.", field="document_id")

        trimmed = document_id.strip()
        if not trimmed:
            return None

        if not cls.VALID_ID_PATTERN.match(trimmed):
            raise ValidationError(
                f"Invalid 'document_id' '{document_id}'. Allowed characters: alphanumeric, hyphens, underscores.",
                field="document_id",
            )
        return trimmed

    @classmethod
    def validate(cls, raw_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Validate complete raw metadata dictionary and return clean validated values."""
        if not isinstance(raw_metadata, dict):
            raise ValidationError("Metadata payload must be a key-value dictionary.")

        clean_title = cls.validate_title(raw_metadata.get("title"))
        clean_filename, doc_format = cls.validate_filename(raw_metadata.get("filename"))
        clean_category = cls.validate_category(raw_metadata.get("policy_category"))
        clean_effective_date = cls.validate_effective_date(raw_metadata.get("effective_date"))
        clean_version = cls.validate_version(raw_metadata.get("version"))
        clean_doc_id = cls.validate_document_id(raw_metadata.get("document_id"))

        extra_metadata = raw_metadata.get("metadata")
        if extra_metadata is not None and not isinstance(extra_metadata, dict):
            raise ValidationError("Field 'metadata' must be a dictionary when provided.", field="metadata")

        return {
            "document_id": clean_doc_id,
            "title": clean_title,
            "filename": clean_filename,
            "file_format": doc_format,
            "policy_category": clean_category,
            "effective_date": clean_effective_date,
            "version": clean_version,
            "metadata": extra_metadata or {},
        }
