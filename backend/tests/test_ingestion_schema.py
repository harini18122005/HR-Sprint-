"""Unit tests for HR policy schemas, metadata validation, and chunk provenance."""

import unittest

from backend.ingestion.service import prepare_policy_document
from backend.ingestion.validator import PolicyMetadataValidator, ValidationError
from backend.schemas.chunk import PolicyChunk, SourceMetadata
from backend.schemas.document import DocumentFormat, IngestionStatus, PolicyCategory, PolicyDocument


class TestPolicyMetadataValidation(unittest.TestCase):
    """Test suite for policy document metadata validation rules."""

    def test_valid_metadata_full(self) -> None:
        """Verify full valid fictional metadata produces a complete PolicyDocument."""
        raw = {
            "document_id": "doc_pto_2026_v2",
            "title": "Nexus Corp Paid Time Off (PTO) Policy",
            "filename": "paid_time_off_policy.pdf",
            "policy_category": "leave",
            "version": "v2.1",
            "effective_date": "2026-01-01",
            "metadata": {
                "department": "People & Culture",
                "jurisdiction": "Global Fictional",
            },
        }

        doc = prepare_policy_document(raw)

        self.assertIsInstance(doc, PolicyDocument)
        self.assertEqual(doc.document_id, "doc_pto_2026_v2")
        self.assertEqual(doc.title, "Nexus Corp Paid Time Off (PTO) Policy")
        self.assertEqual(doc.filename, "paid_time_off_policy.pdf")
        self.assertEqual(doc.policy_category, PolicyCategory.LEAVE)
        self.assertEqual(doc.file_format, DocumentFormat.PDF)
        self.assertEqual(doc.version, "v2.1")
        self.assertEqual(doc.effective_date, "2026-01-01")
        self.assertEqual(doc.ingestion_status, IngestionStatus.VALIDATED)
        self.assertEqual(doc.metadata.get("department"), "People & Culture")

    def test_valid_metadata_minimal_generates_id_and_defaults(self) -> None:
        """Verify minimal required metadata autogenerates document_id and handles defaults."""
        raw = {
            "title": "Remote & Flexible Work Standards",
            "filename": "remote_work_standards.md",
            "policy_category": "remote_work",
        }

        doc = prepare_policy_document(raw)

        self.assertIsInstance(doc, PolicyDocument)
        self.assertTrue(doc.document_id.startswith("doc_remote_work_"))
        self.assertEqual(doc.policy_category, PolicyCategory.REMOTE_WORK)
        self.assertEqual(doc.file_format, DocumentFormat.MD)
        self.assertIsNone(doc.version)
        self.assertIsNone(doc.effective_date)
        self.assertEqual(doc.ingestion_status, IngestionStatus.VALIDATED)
        self.assertEqual(doc.metadata, {})

    def test_supported_document_formats(self) -> None:
        """Verify all defined supported formats are accepted (.pdf, .md, .txt, .docx)."""
        formats = [
            ("sample.pdf", DocumentFormat.PDF),
            ("sample.md", DocumentFormat.MD),
            ("sample.txt", DocumentFormat.TXT),
            ("sample.docx", DocumentFormat.DOCX),
        ]
        for filename, expected_format in formats:
            raw = {
                "title": "Sample Fictional Policy",
                "filename": filename,
                "policy_category": "general",
            }
            doc = prepare_policy_document(raw)
            self.assertEqual(doc.file_format, expected_format)

    def test_missing_required_fields(self) -> None:
        """Verify missing or empty required fields raise ValidationError."""
        # Missing title
        with self.assertRaises(ValidationError) as ctx:
            prepare_policy_document({
                "filename": "benefits.pdf",
                "policy_category": "benefits",
            })
        self.assertEqual(ctx.exception.field, "title")

        # Empty title
        with self.assertRaises(ValidationError) as ctx:
            prepare_policy_document({
                "title": "   ",
                "filename": "benefits.pdf",
                "policy_category": "benefits",
            })
        self.assertEqual(ctx.exception.field, "title")

        # Missing filename
        with self.assertRaises(ValidationError) as ctx:
            prepare_policy_document({
                "title": "Comprehensive Benefits Guide",
                "policy_category": "benefits",
            })
        self.assertEqual(ctx.exception.field, "filename")

        # Empty filename
        with self.assertRaises(ValidationError) as ctx:
            prepare_policy_document({
                "title": "Comprehensive Benefits Guide",
                "filename": "  ",
                "policy_category": "benefits",
            })
        self.assertEqual(ctx.exception.field, "filename")

        # Missing policy_category
        with self.assertRaises(ValidationError) as ctx:
            prepare_policy_document({
                "title": "Comprehensive Benefits Guide",
                "filename": "benefits.pdf",
            })
        self.assertEqual(ctx.exception.field, "policy_category")

    def test_unsupported_file_types(self) -> None:
        """Verify unsupported extensions are rejected."""
        unsupported = [
            "policy.exe",
            "policy.png",
            "policy.xlsx",
            "policy.zip",
            "policy.sh",
            "policy_without_extension",
        ]
        for bad_filename in unsupported:
            with self.assertRaises(ValidationError) as ctx:
                prepare_policy_document({
                    "title": "Fictional Policy",
                    "filename": bad_filename,
                    "policy_category": "benefits",
                })
            self.assertEqual(ctx.exception.field, "filename")

    def test_invalid_metadata_values(self) -> None:
        """Verify malformed metadata values trigger informative ValidationError."""
        # Invalid date format
        invalid_dates = ["2026/01/01", "01-01-2026", "2026-02-30", "not-a-date"]
        for bad_date in invalid_dates:
            with self.assertRaises(ValidationError) as ctx:
                prepare_policy_document({
                    "title": "Parental Leave Policy",
                    "filename": "parental_leave.pdf",
                    "policy_category": "leave",
                    "effective_date": bad_date,
                })
            self.assertEqual(ctx.exception.field, "effective_date")

        # Invalid policy category
        with self.assertRaises(ValidationError) as ctx:
            prepare_policy_document({
                "title": "Parental Leave Policy",
                "filename": "parental_leave.pdf",
                "policy_category": "crypto_trading",
            })
        self.assertEqual(ctx.exception.field, "policy_category")

        # Path traversal in filename
        unsafe_filenames = [
            "../secret.pdf",
            "..\\secret.pdf",
            "policies/leave.pdf",
            "/etc/passwd.pdf",
            "C:\\Windows\\system32\\policy.pdf",
        ]
        for unsafe in unsafe_filenames:
            with self.assertRaises(ValidationError) as ctx:
                prepare_policy_document({
                    "title": "Parental Leave Policy",
                    "filename": unsafe,
                    "policy_category": "leave",
                })
            self.assertEqual(ctx.exception.field, "filename")

        # Invalid document_id characters
        with self.assertRaises(ValidationError) as ctx:
            prepare_policy_document({
                "document_id": "doc with spaces!",
                "title": "Parental Leave Policy",
                "filename": "parental_leave.pdf",
                "policy_category": "leave",
            })
        self.assertEqual(ctx.exception.field, "document_id")

        # Non-dict payload
        with self.assertRaises(ValidationError):
            PolicyMetadataValidator.validate("invalid_payload")  # type: ignore[arg-type]


class TestPolicyChunkSchema(unittest.TestCase):
    """Test suite for policy chunk schema, ordering, and source traceability."""

    def test_chunk_with_page_number_and_section_citation(self) -> None:
        """Verify chunk with page number formats accurate source citation."""
        source = SourceMetadata(
            document_id="doc_leave_pto_001",
            document_title="Nexus Corp Paid Time Off Policy",
            filename="pto_policy_2026.pdf",
            policy_category="leave",
            version="v2.0",
            effective_date="2026-01-01",
            page_number=4,
            section_header="3.1 Accrual Rates and Maximum Rollover",
        )

        chunk = PolicyChunk(
            chunk_id="chk_pto_004",
            document_id="doc_leave_pto_001",
            chunk_text="Full-time employees accrue 15 days of PTO annually, up to a maximum rollover of 5 days.",
            chunk_order=3,
            page_number=4,
            section_header="3.1 Accrual Rates and Maximum Rollover",
            source_metadata=source,
        )

        expected_citation = (
            "Nexus Corp Paid Time Off Policy (v2.0) | "
            "Section: 3.1 Accrual Rates and Maximum Rollover | "
            "Page 4"
        )
        self.assertEqual(chunk.get_citation_reference(), expected_citation)
        self.assertEqual(chunk.page_number, 4)
        self.assertEqual(chunk.chunk_order, 3)

    def test_chunk_without_page_number_does_not_fabricate_page(self) -> None:
        """Verify chunk from page-less formats (e.g. Markdown) omits page from citation."""
        source = SourceMetadata(
            document_id="doc_remote_001",
            document_title="Remote Work Standards",
            filename="remote_work.md",
            policy_category="remote_work",
            version="1.0",
            page_number=None,
            section_header="Core Hours and Availability",
        )

        chunk = PolicyChunk(
            chunk_id="chk_remote_002",
            document_id="doc_remote_001",
            chunk_text="Core working hours are 10:00 AM to 3:00 PM local time across distributed teams.",
            chunk_order=1,
            page_number=None,  # No page number available
            section_header="Core Hours and Availability",
            source_metadata=source,
        )

        expected_citation = "Remote Work Standards (1.0) | Section: Core Hours and Availability"
        self.assertEqual(chunk.get_citation_reference(), expected_citation)
        self.assertNotIn("Page", chunk.get_citation_reference())
        self.assertIsNone(chunk.page_number)

    def test_chunk_validation_constraints(self) -> None:
        """Verify invalid chunk attributes raise ValueError."""
        # Empty chunk_id
        with self.assertRaises(ValueError):
            PolicyChunk(
                chunk_id="",
                document_id="doc_1",
                chunk_text="Valid passage",
                chunk_order=0,
            )

        # Empty document_id
        with self.assertRaises(ValueError):
            PolicyChunk(
                chunk_id="chk_1",
                document_id="  ",
                chunk_text="Valid passage",
                chunk_order=0,
            )

        # Empty chunk_text
        with self.assertRaises(ValueError):
            PolicyChunk(
                chunk_id="chk_1",
                document_id="doc_1",
                chunk_text="   ",
                chunk_order=0,
            )

        # Negative chunk order
        with self.assertRaises(ValueError):
            PolicyChunk(
                chunk_id="chk_1",
                document_id="doc_1",
                chunk_text="Valid passage",
                chunk_order=-1,
            )

        # Non-positive page number (e.g., 0)
        with self.assertRaises(ValueError):
            PolicyChunk(
                chunk_id="chk_1",
                document_id="doc_1",
                chunk_text="Valid passage",
                chunk_order=0,
                page_number=0,
            )

    def test_serialization(self) -> None:
        """Verify to_dict returns clean, serializable dictionaries for documents and chunks."""
        raw_doc = {
            "document_id": "doc_code_01",
            "title": "Code of Business Conduct",
            "filename": "code_of_conduct.txt",
            "policy_category": "code_of_conduct",
        }
        doc = prepare_policy_document(raw_doc)
        doc_dict = doc.to_dict()

        self.assertEqual(doc_dict["document_id"], "doc_code_01")
        self.assertEqual(doc_dict["policy_category"], "code_of_conduct")
        self.assertEqual(doc_dict["file_format"], ".txt")
        self.assertEqual(doc_dict["ingestion_status"], "validated")

        chunk = PolicyChunk(
            chunk_id="chk_code_01",
            document_id="doc_code_01",
            chunk_text="Employees must uphold honesty and professional integrity.",
            chunk_order=0,
        )
        chunk_dict = chunk.to_dict()
        self.assertEqual(chunk_dict["chunk_id"], "chk_code_01")
        self.assertEqual(chunk_dict["chunk_order"], 0)


if __name__ == "__main__":
    unittest.main()
