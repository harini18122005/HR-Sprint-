"""Document schema for HR Policy AI Assistant."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class PolicyCategory(str, Enum):
    """Fictional company HR policy domain categories."""

    LEAVE = "leave"
    ATTENDANCE = "attendance"
    BENEFITS = "benefits"
    REMOTE_WORK = "remote_work"
    CODE_OF_CONDUCT = "code_of_conduct"
    COMPENSATION = "compensation"
    HEALTH_AND_SAFETY = "health_and_safety"
    GENERAL = "general"


class IngestionStatus(str, Enum):
    """Lifecycle status of a policy document through the ingestion pipeline."""

    PENDING = "pending"
    VALIDATED = "validated"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentFormat(str, Enum):
    """Supported document formats for HR policies."""

    PDF = ".pdf"
    MD = ".md"
    TXT = ".txt"
    DOCX = ".docx"

    @classmethod
    def has_extension(cls, ext: str) -> bool:
        """Check if an extension (including dot, case-insensitive) is supported."""
        normalized = ext.lower().strip()
        return any(item.value == normalized for item in cls)


@dataclass
class PolicyDocument:
    """Schema representing an ingested HR policy document.

    Attributes:
        document_id: Unique string identifier for the document (UUID or slug).
        title: Human-readable official title of the HR policy.
        filename: Name of the policy document file with extension.
        policy_category: Category classifying the policy area.
        file_format: Standardized file format extension.
        version: Document version string (e.g., 'v2.0', '2026.1'), optional.
        effective_date: ISO 8601 date string (YYYY-MM-DD) when the policy takes effect, optional.
        ingestion_status: Current status within the ingestion pipeline.
        metadata: Arbitrary additional metadata (e.g., department, author), optional.
        created_at: ISO timestamp recording when the record was prepared.
    """

    document_id: str
    title: str
    filename: str
    policy_category: PolicyCategory
    file_format: DocumentFormat
    version: Optional[str] = None
    effective_date: Optional[str] = None
    ingestion_status: IngestionStatus = IngestionStatus.VALIDATED
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert the policy document schema to a serializable dictionary."""
        data = asdict(self)
        data["policy_category"] = self.policy_category.value
        data["file_format"] = self.file_format.value
        data["ingestion_status"] = self.ingestion_status.value
        return data
