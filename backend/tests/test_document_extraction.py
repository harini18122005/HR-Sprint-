"""Unit tests for HR policy document text extraction and provenance preservation."""

from pathlib import Path
import tempfile
import unittest

from backend.ingestion.extractor import (
    ExtractedDocument,
    ExtractionError,
    PDFDocumentExtractor,
    PolicyDocumentExtractor,
    TextDocumentExtractor,
    extract_policy_document,
    normalize_text,
)
from backend.ingestion.service import prepare_policy_document
from backend.schemas.chunk import PolicyChunk
from backend.schemas.document import DocumentFormat, PolicyCategory, PolicyDocument


class TestDocumentExtraction(unittest.TestCase):
    """Test suite for policy document extraction, normalization, and provenance."""

    def setUp(self) -> None:
        """Locate sample policies directory relative to this test file."""
        self.repo_root = Path(__file__).resolve().parent.parent.parent
        self.sample_policies_dir = self.repo_root / "sample-policies"

    def test_extract_markdown_sample_leave_policy(self) -> None:
        """Verify extraction from Markdown sample leave policy."""
        file_path = self.sample_policies_dir / "leave_policy.md"
        self.assertTrue(file_path.exists(), f"Sample policy {file_path} not found.")

        extracted = PolicyDocumentExtractor.extract(file_path)

        self.assertIsInstance(extracted, ExtractedDocument)
        self.assertEqual(extracted.filename, "leave_policy.md")
        self.assertEqual(extracted.file_format, DocumentFormat.MD)
        self.assertIn("Acme Global Technologies", extracted.text)
        self.assertIn("Paid Time Off (PTO) Accrual", extracted.text)
        self.assertIn("Parental Leave", extracted.text)

        # Markdown documents have no inherent page numbers; must strictly be None
        self.assertIsNone(extracted.page_count)
        self.assertIsNone(extracted.pages)

        # Metadata metrics
        self.assertGreater(extracted.metadata["character_count"], 500)
        self.assertGreater(extracted.metadata["word_count"], 100)
        self.assertGreater(extracted.metadata["line_count"], 10)
        self.assertIn(extracted.metadata["encoding"], ("utf-8", "utf-8-sig"))

    def test_extract_markdown_sample_attendance_policy(self) -> None:
        """Verify extraction from Markdown sample attendance policy."""
        file_path = self.sample_policies_dir / "attendance_policy.md"
        self.assertTrue(file_path.exists())

        extracted = PolicyDocumentExtractor.extract(file_path)

        self.assertIsInstance(extracted, ExtractedDocument)
        self.assertEqual(extracted.filename, "attendance_policy.md")
        self.assertEqual(extracted.file_format, DocumentFormat.MD)
        self.assertIn("Core Collaboration Window", extracted.text)
        self.assertIn("10:00 AM to 3:00 PM", extracted.text)
        self.assertIsNone(extracted.page_count)

    def test_extract_markdown_sample_benefits_policy(self) -> None:
        """Verify extraction from Markdown sample benefits policy."""
        file_path = self.sample_policies_dir / "employee_benefits_policy.md"
        self.assertTrue(file_path.exists())

        extracted = PolicyDocumentExtractor.extract(file_path)

        self.assertIsInstance(extracted, ExtractedDocument)
        self.assertEqual(extracted.filename, "employee_benefits_policy.md")
        self.assertEqual(extracted.file_format, DocumentFormat.MD)
        self.assertIn("Comprehensive Employee Benefits Guide", extracted.text)
        self.assertIn("401(k) Savings Plan", extracted.text)
        self.assertIsNone(extracted.page_count)

    def test_extract_txt_sample_code_of_conduct(self) -> None:
        """Verify extraction from plain text sample policy."""
        file_path = self.sample_policies_dir / "code_of_conduct_policy.txt"
        self.assertTrue(file_path.exists())

        extracted = PolicyDocumentExtractor.extract(file_path)

        self.assertIsInstance(extracted, ExtractedDocument)
        self.assertEqual(extracted.filename, "code_of_conduct_policy.txt")
        self.assertEqual(extracted.file_format, DocumentFormat.TXT)
        self.assertIn("CODE OF BUSINESS CONDUCT AND ETHICS", extracted.text)
        self.assertIn("SECTION 1: COMMITMENT TO INTEGRITY AND RESPECT", extracted.text)
        self.assertIsNone(extracted.page_count)

    def test_all_sample_policies_in_directory_are_valid(self) -> None:
        """Ensure all policies stored in sample-policies/ extract successfully."""
        policy_files = list(self.sample_policies_dir.glob("*.md")) + list(
            self.sample_policies_dir.glob("*.txt")
        )
        self.assertGreaterEqual(len(policy_files), 3)

        for p_file in policy_files:
            extracted = PolicyDocumentExtractor.extract(p_file)
            self.assertGreater(
                len(extracted.text),
                100,
                f"Policy {p_file.name} extracted text unexpectedly brief.",
            )
            self.assertIn(extracted.file_format, (DocumentFormat.MD, DocumentFormat.TXT))

    def test_empty_document_raises_extraction_error(self) -> None:
        """Verify 0-byte document raises informative ExtractionError."""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with self.assertRaises(ExtractionError) as ctx:
                PolicyDocumentExtractor.extract(tmp_path)
            self.assertIn("empty", str(ctx.exception).lower())
            self.assertEqual(ctx.exception.filename, tmp_path.name)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_whitespace_only_document_raises_extraction_error(self) -> None:
        """Verify document containing only whitespace raises ExtractionError."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            encoding="utf-8",
            delete=False,
        ) as tmp:
            tmp.write("   \n\n  \t\t \n   ")
            tmp_path = Path(tmp.name)

        try:
            with self.assertRaises(ExtractionError) as ctx:
                PolicyDocumentExtractor.extract(tmp_path)
            self.assertIn("whitespace", str(ctx.exception).lower())
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_missing_file_raises_extraction_error(self) -> None:
        """Verify attempting to extract non-existent file raises ExtractionError."""
        missing = self.sample_policies_dir / "non_existent_policy_file.md"
        with self.assertRaises(ExtractionError) as ctx:
            PolicyDocumentExtractor.extract(missing)
        self.assertIn("not found", str(ctx.exception).lower())

    def test_directory_path_raises_extraction_error(self) -> None:
        """Verify passing a directory path raises ExtractionError."""
        with self.assertRaises(ExtractionError) as ctx:
            PolicyDocumentExtractor.extract(self.sample_policies_dir)
        self.assertIn("directory", str(ctx.exception).lower())

    def test_unsupported_extension_raises_extraction_error(self) -> None:
        """Verify unsupported formats (.exe, .zip, .png) raise ExtractionError."""
        bad_extensions = [".exe", ".zip", ".png", ".xlsx", ".json"]
        for ext in bad_extensions:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(b"content")
                tmp_path = Path(tmp.name)
            try:
                with self.assertRaises(ExtractionError) as ctx:
                    PolicyDocumentExtractor.extract(tmp_path)
                self.assertIn("unsupported", str(ctx.exception).lower())
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

    def test_invalid_utf8_encoding_raises_extraction_error(self) -> None:
        """Verify invalid byte sequence that fails UTF-8 decoding raises ExtractionError."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            # High invalid byte sequence in UTF-8
            tmp.write(b"\x80\x81\xFF\xFE\xAA\xBB")
            tmp_path = Path(tmp.name)

        try:
            with self.assertRaises(ExtractionError) as ctx:
                PolicyDocumentExtractor.extract(tmp_path)
            self.assertIn("decode", str(ctx.exception).lower())
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_utf8_bom_handled_gracefully(self) -> None:
        """Verify UTF-8 with BOM is decoded cleanly without leading BOM character."""
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".md",
            delete=False,
        ) as tmp:
            # UTF-8 BOM is \xef\xbb\xbf
            bom = b"\xef\xbb\xbf# Policy with BOM\nValid content here."
            tmp.write(bom)
            tmp_path = Path(tmp.name)

        try:
            extracted = PolicyDocumentExtractor.extract(tmp_path)
            self.assertTrue(extracted.text.startswith("# Policy with BOM"))
            self.assertNotIn("\ufeff", extracted.text)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_normalization_rules(self) -> None:
        """Verify normalization unifies line breaks, collapses blank lines, and removes trailing spaces."""
        raw = (
            "Line 1 with trailing spaces.   \r\n"
            "Line 2 with NBSP:\u00a0value.\r\n"
            "\r\n"
            "\r\n"
            "\r\n"
            "Line 3 after excessive newlines."
        )
        normalized = normalize_text(raw)
        expected = (
            "Line 1 with trailing spaces.\n"
            "Line 2 with NBSP: value.\n\n"
            "Line 3 after excessive newlines."
        )
        self.assertEqual(normalized, expected)

    def test_source_provenance_connected_to_raw_chunk(self) -> None:
        """Verify extraction output connects seamlessly to PolicyDocument and PolicyChunk."""
        file_path = self.sample_policies_dir / "leave_policy.md"
        doc = prepare_policy_document({
            "document_id": "doc_leave_acme_2026",
            "title": "Acme Global Paid Time Off and Leave Policy",
            "filename": "leave_policy.md",
            "policy_category": "leave",
            "version": "2.1",
            "effective_date": "2026-01-01",
        })

        extracted, raw_chunk = extract_policy_document(file_path, document=doc)

        self.assertIsNotNone(raw_chunk)
        self.assertIsInstance(raw_chunk, PolicyChunk)
        self.assertEqual(raw_chunk.document_id, "doc_leave_acme_2026")
        self.assertEqual(raw_chunk.chunk_text, extracted.text)
        self.assertEqual(raw_chunk.chunk_order, 0)

        # CRITICAL: Page numbers must not be fabricated for Markdown
        self.assertIsNone(raw_chunk.page_number)

        # Source metadata validation
        self.assertIsNotNone(raw_chunk.source_metadata)
        self.assertEqual(
            raw_chunk.source_metadata.document_title,
            "Acme Global Paid Time Off and Leave Policy",
        )
        self.assertEqual(raw_chunk.source_metadata.policy_category, "leave")
        self.assertEqual(raw_chunk.source_metadata.version, "2.1")
        self.assertIsNone(raw_chunk.source_metadata.page_number)

        # Formatted citation check: must NOT include "Page"
        citation = raw_chunk.get_citation_reference()
        self.assertIn("Acme Global Paid Time Off and Leave Policy (2.1)", citation)
        self.assertNotIn("Page", citation)

    def test_pdf_extractor_explains_missing_dependency(self) -> None:
        """Verify PDF extractor raises actionable error if pypdf is not present."""
        # Test behavior when encountering PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 header")
            tmp_path = Path(tmp.name)

        try:
            # Whether pypdf is installed or not, it should behave gracefully
            try:
                import pypdf  # noqa: F401
                pypdf_installed = True
            except ImportError:
                pypdf_installed = False

            if not pypdf_installed:
                with self.assertRaises(ExtractionError) as ctx:
                    PDFDocumentExtractor.extract(tmp_path)
                self.assertIn("pypdf", str(ctx.exception).lower())
            else:
                # If installed in env, ensure it attempts extraction
                self.assertTrue(PDFDocumentExtractor.can_extract(DocumentFormat.PDF))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


if __name__ == "__main__":
    unittest.main()
