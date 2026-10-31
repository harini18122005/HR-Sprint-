"""Unit tests for HR policy text chunking, overlap, and provenance preservation."""

from pathlib import Path
import unittest

from backend.ingestion.chunker import (
    ChunkingConfig,
    PolicyChunker,
    chunk_policy_document,
)
from backend.ingestion.extractor import ExtractedDocument, PolicyDocumentExtractor
from backend.ingestion.service import prepare_policy_document
from backend.schemas.chunk import PolicyChunk, SourceMetadata
from backend.schemas.document import DocumentFormat, PolicyCategory, PolicyDocument


class TestPolicyTextChunking(unittest.TestCase):
    """Test suite for policy text chunking, overlap, and metadata preservation."""

    def setUp(self) -> None:
        """Locate sample policies directory relative to this test file."""
        self.repo_root = Path(__file__).resolve().parent.parent.parent
        self.sample_policies_dir = self.repo_root / "sample-policies"

    def test_default_config_values(self) -> None:
        """Verify default configuration values (~500 chunk size, ~100 overlap)."""
        config = ChunkingConfig()
        self.assertEqual(config.chunk_size, 500)
        self.assertEqual(config.chunk_overlap, 100)
        self.assertEqual(config.min_chunk_size, 50)

    def test_invalid_config_values_raise_value_error(self) -> None:
        """Verify invalid configuration parameters raise descriptive ValueErrors."""
        # chunk_size <= 0
        with self.assertRaises(ValueError) as ctx:
            ChunkingConfig(chunk_size=0)
        self.assertIn("positive", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ChunkingConfig(chunk_size=100.5)
        self.assertIn("integer", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ChunkingConfig(chunk_overlap=True)
        self.assertIn("integer", str(ctx.exception))

        # chunk_overlap < 0
        with self.assertRaises(ValueError) as ctx:
            ChunkingConfig(chunk_overlap=-10)
        self.assertIn("non-negative", str(ctx.exception))

        # chunk_overlap >= chunk_size
        with self.assertRaises(ValueError) as ctx:
            ChunkingConfig(chunk_size=200, chunk_overlap=200)
        self.assertIn("strictly less than", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ChunkingConfig(chunk_size=200, chunk_overlap=250)
        self.assertIn("strictly less than", str(ctx.exception))

        # min_chunk_size > chunk_size
        with self.assertRaises(ValueError) as ctx:
            ChunkingConfig(chunk_size=300, chunk_overlap=50, min_chunk_size=350)
        self.assertIn("cannot exceed", str(ctx.exception))

    def test_empty_and_whitespace_text(self) -> None:
        """Verify empty or whitespace-only text returns an empty list of chunks."""
        chunker = PolicyChunker()
        self.assertEqual(chunker.chunk_text("", document_id="doc_test"), [])
        self.assertEqual(chunker.chunk_text("   \n\t\n   ", document_id="doc_test"), [])

    def test_short_document_produces_single_chunk(self) -> None:
        """Verify short documents (< chunk_size) produce exactly 1 chunk with order 0."""
        short_text = "This is a short policy statement regarding company ID badges and office access."
        chunker = PolicyChunker(ChunkingConfig(chunk_size=500, chunk_overlap=100))

        chunks = chunker.chunk_text(short_text, document_id="doc_badges_001")

        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertIsInstance(chunk, PolicyChunk)
        self.assertEqual(chunk.chunk_order, 0)
        self.assertEqual(chunk.document_id, "doc_badges_001")
        self.assertEqual(chunk.chunk_id, "chk_doc_badges_001_000")
        self.assertEqual(chunk.chunk_text, short_text)

    def test_sequential_chunk_ordering_and_unique_ids(self) -> None:
        """Verify sequential ordering (0, 1, 2...) and uniqueness of chunk IDs."""
        sample_file = self.sample_policies_dir / "leave_policy.md"
        extracted = PolicyDocumentExtractor.extract(sample_file)

        chunker = PolicyChunker(ChunkingConfig(chunk_size=400, chunk_overlap=80))
        chunks = chunker.chunk_text(extracted.text, document_id="doc_leave_test")

        self.assertGreaterEqual(len(chunks), 3)

        chunk_ids = [c.chunk_id for c in chunks]
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)), "Chunk IDs must be unique.")

        for idx, chunk in enumerate(chunks):
            self.assertEqual(chunk.chunk_order, idx, f"Chunk {idx} order mismatch.")
            self.assertEqual(chunk.document_id, "doc_leave_test")
            self.assertEqual(chunk.chunk_id, f"chk_doc_leave_test_{idx:03d}")
            self.assertGreater(len(chunk.chunk_text.strip()), 0)

    def test_consecutive_chunks_have_overlap(self) -> None:
        """Verify consecutive chunks share overlapping content."""
        sample_file = self.sample_policies_dir / "attendance_policy.md"
        extracted = PolicyDocumentExtractor.extract(sample_file)

        chunker = PolicyChunker(ChunkingConfig(chunk_size=400, chunk_overlap=100))
        chunks = chunker.chunk_text(extracted.text, document_id="doc_att_test")

        self.assertGreaterEqual(len(chunks), 2)

        # Check overlap between pairs of consecutive chunks
        for i in range(len(chunks) - 1):
            chunk_a = chunks[i].chunk_text
            chunk_b = chunks[i + 1].chunk_text

            # Extract words from the end of chunk_a
            words_a = [w for w in chunk_a.split() if len(w) > 3][-10:]
            # Ensure at least some key words or phrases from the tail of chunk A exist in chunk B
            shared_words = [w for w in words_a if w in chunk_b]
            self.assertGreater(
                len(shared_words),
                0,
                f"Expected overlap between chunk {i} and {i+1}, found no shared words.",
            )

    def test_preservation_of_document_id_and_source_metadata(self) -> None:
        """Verify chunks retain complete source metadata without fabricating page numbers."""
        sample_file = self.sample_policies_dir / "employee_benefits_policy.md"
        extracted = PolicyDocumentExtractor.extract(sample_file)

        doc = prepare_policy_document({
            "document_id": "doc_benefits_2026",
            "title": "Comprehensive Employee Benefits Guide",
            "filename": "employee_benefits_policy.md",
            "policy_category": "benefits",
            "version": "3.0",
            "effective_date": "2026-01-01",
        })

        chunks = chunk_policy_document(extracted, doc)
        self.assertGreater(len(chunks), 1)

        for chunk in chunks:
            self.assertEqual(chunk.document_id, "doc_benefits_2026")
            self.assertIsNotNone(chunk.source_metadata)
            self.assertEqual(
                chunk.source_metadata.document_title,
                "Comprehensive Employee Benefits Guide",
            )
            self.assertEqual(chunk.source_metadata.policy_category, "benefits")
            self.assertEqual(chunk.source_metadata.version, "3.0")

            # CRITICAL: Page number must NOT be fabricated for Markdown
            self.assertIsNone(chunk.page_number)
            self.assertIsNone(chunk.source_metadata.page_number)

            citation = chunk.get_citation_reference()
            self.assertIn("Comprehensive Employee Benefits Guide", citation)
            self.assertNotIn("Page", citation)

    def test_pdf_page_numbers_require_page_bounded_text(self) -> None:
        """Page counts alone do not establish page provenance for individual chunks."""
        doc = prepare_policy_document({
            "document_id": "doc_pdf_pages",
            "title": "PDF Policy",
            "filename": "policy.pdf",
            "policy_category": "general",
        })
        chunker = PolicyChunker(ChunkingConfig(
            chunk_size=30,
            chunk_overlap=5,
            min_chunk_size=1,
        ))

        page_bounded = ExtractedDocument(
            text="First page policy text.\n\nSecond page policy text.",
            filename="policy.pdf",
            file_format=DocumentFormat.PDF,
            page_count=2,
            pages=[(1, "First page policy text."), (2, "Second page policy text.")],
        )
        page_chunks = chunker.chunk_document(page_bounded, doc)
        self.assertEqual([chunk.page_number for chunk in page_chunks], [1, 2])
        self.assertEqual(
            [chunk.source_metadata.page_number for chunk in page_chunks],
            [1, 2],
        )

        count_only = ExtractedDocument(
            text="Extracted PDF text without page boundaries.",
            filename="policy.pdf",
            file_format=DocumentFormat.PDF,
            page_count=2,
        )
        count_only_chunks = chunker.chunk_document(count_only, doc)
        self.assertTrue(count_only_chunks)
        self.assertTrue(all(chunk.page_number is None for chunk in count_only_chunks))
        self.assertTrue(
            all(chunk.source_metadata.page_number is None for chunk in count_only_chunks)
        )

    def test_markdown_section_header_detection(self) -> None:
        """Verify section headings (# and ##) are tracked and attached to respective chunks."""
        text = (
            "# Acme Corp Handbook\n\n"
            "Introductory general policy paragraph.\n\n"
            "## 1. Core Working Hours\n\n"
            "Employees are expected to be online during core collaboration hours from 10:00 AM to 3:00 PM.\n"
            "During this window, synchronous communication is required across all remote and hybrid teams.\n\n"
            "## 2. Overtime Rules\n\n"
            "Non-exempt personnel must receive managerial pre-authorization prior to working overtime.\n"
            "Overtime is compensated at time-and-a-half rate."
        )

        chunker = PolicyChunker(ChunkingConfig(chunk_size=250, chunk_overlap=50))
        chunks = chunker.chunk_text(text, document_id="doc_handbook_01")

        self.assertGreaterEqual(len(chunks), 2)
        # Verify that section headers are populated and correspond to the text
        headers_found = [c.section_header for c in chunks if c.section_header]
        self.assertTrue(any("Core Working Hours" in h for h in headers_found))
        self.assertTrue(any("Overtime Rules" in h for h in headers_found))

    def test_plain_text_section_header_detection(self) -> None:
        """Verify plaintext headers (e.g. SECTION 1: ...) are detected and attached."""
        sample_file = self.sample_policies_dir / "code_of_conduct_policy.txt"
        extracted = PolicyDocumentExtractor.extract(sample_file)

        doc = prepare_policy_document({
            "document_id": "doc_ethics_01",
            "title": "Code of Business Conduct",
            "filename": "code_of_conduct_policy.txt",
            "policy_category": "code_of_conduct",
        })

        chunks = chunk_policy_document(extracted, doc)
        self.assertGreater(len(chunks), 1)

        section_headers = [c.section_header for c in chunks if c.section_header]
        self.assertGreater(len(section_headers), 0)
        self.assertTrue(any("SECTION" in h for h in section_headers))

    def test_long_paragraphs_split_cleanly(self) -> None:
        """Verify an oversized single paragraph splits without exceeding chunk_size excessively."""
        # Single long paragraph of 1200 characters without double-newlines
        sentence = "Employees must adhere strictly to established data security protocols. "
        long_paragraph = sentence * 16  # ~1150 chars

        chunker = PolicyChunker(ChunkingConfig(chunk_size=400, chunk_overlap=80))
        chunks = chunker.chunk_text(long_paragraph, document_id="doc_long_para")

        self.assertGreaterEqual(len(chunks), 3)
        for chunk in chunks:
            # Each chunk should reasonably respect chunk_size
            self.assertLessEqual(len(chunk.chunk_text), 500)
            self.assertGreater(len(chunk.chunk_text), 0)

    def test_all_sample_policies_chunk_successfully(self) -> None:
        """Verify all 4 sample policy documents chunk cleanly with valid output."""
        policy_files = [
            ("leave_policy.md", "leave"),
            ("attendance_policy.md", "attendance"),
            ("employee_benefits_policy.md", "benefits"),
            ("code_of_conduct_policy.txt", "code_of_conduct"),
        ]

        chunker = PolicyChunker()

        for filename, category in policy_files:
            file_path = self.sample_policies_dir / filename
            self.assertTrue(file_path.exists())

            extracted = PolicyDocumentExtractor.extract(file_path)
            doc = prepare_policy_document({
                "title": f"Fictional {filename}",
                "filename": filename,
                "policy_category": category,
            })

            chunks = chunker.chunk_document(extracted, doc)

            self.assertGreaterEqual(
                len(chunks),
                2,
                f"Policy {filename} should produce multiple chunks.",
            )

            # Validate each chunk integrity
            for idx, c in enumerate(chunks):
                self.assertEqual(c.chunk_order, idx)
                self.assertEqual(c.document_id, doc.document_id)
                self.assertTrue(c.chunk_id.startswith(f"chk_{doc.document_id}_"))
                self.assertIsNotNone(c.source_metadata)
                self.assertIsNone(c.page_number)

    def test_custom_chunk_size_and_overlap_override(self) -> None:
        """Verify custom chunk size and overlap are strictly respected."""
        sample_file = self.sample_policies_dir / "leave_policy.md"
        extracted = PolicyDocumentExtractor.extract(sample_file)

        custom_config = ChunkingConfig(chunk_size=300, chunk_overlap=50)
        chunker = PolicyChunker(config=custom_config)

        chunks = chunker.chunk_text(extracted.text, document_id="doc_custom")
        self.assertGreater(len(chunks), 5)

        for chunk in chunks:
            # Allow modest slack for single sentence boundaries, but ensure bound is respected
            self.assertLessEqual(len(chunk.chunk_text), 380)


if __name__ == "__main__":
    unittest.main()
