"""Tests for lexical policy retrieval and source traceability."""

from pathlib import Path
import unittest

from backend.ingestion.chunker import PolicyChunker
from backend.ingestion.extractor import PolicyDocumentExtractor
from backend.ingestion.service import prepare_policy_document
from backend.retrieval import PolicyRetriever, RetrievedPolicyChunk
from backend.schemas.chunk import PolicyChunk, SourceMetadata


class TestPolicyRetrieval(unittest.TestCase):
    """Exercise retrieval against chunks produced by the real ingestion pipeline."""

    @classmethod
    def setUpClass(cls) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        samples = (
            ("leave_policy.md", "leave", "doc_leave_test", "Acme Leave Policy"),
            ("attendance_policy.md", "attendance", "doc_attendance_test", "Acme Attendance Policy"),
            ("employee_benefits_policy.md", "benefits", "doc_benefits_test", "Acme Benefits Guide"),
        )
        chunker = PolicyChunker()
        cls.chunks = []
        for filename, category, document_id, title in samples:
            extracted = PolicyDocumentExtractor.extract(repo_root / "sample-policies" / filename)
            document = prepare_policy_document({
                "document_id": document_id,
                "title": title,
                "filename": filename,
                "policy_category": category,
            })
            cls.chunks.extend(chunker.chunk_document(extracted, document))
        cls.retriever = PolicyRetriever(cls.chunks)

    def test_retrieves_relevant_leave_policy_chunk(self) -> None:
        results = self.retriever.retrieve("How much PTO can I carry over to next year?", category="leave")
        self.assertTrue(results)
        self.assertIn("maximum of 5 unused PTO days", results[0].text)

    def test_retrieves_relevant_attendance_policy_chunk(self) -> None:
        results = self.retriever.retrieve("When do I need to be online for core hours?", category="attendance")
        self.assertTrue(results)
        self.assertIn("10:00 AM to 3:00 PM", results[0].text)

    def test_retrieves_relevant_benefits_policy_chunk(self) -> None:
        results = self.retriever.retrieve("How much is the annual HSA contribution for families?", category="benefits")
        self.assertTrue(results)
        self.assertIn("$2,000 for families", results[0].text)

    def test_more_relevant_chunk_ranks_first(self) -> None:
        chunks = [
            self._make_chunk("less", "PTO accrual depends on years of service and pay periods."),
            self._make_chunk("more", "Employees may carry over a maximum of 5 unused PTO days into the next calendar year."),
        ]
        results = PolicyRetriever(chunks).retrieve("maximum PTO days carry over next year")
        self.assertEqual(results[0].chunk_id, "more")
        self.assertGreater(results[0].relevance_score, results[1].relevance_score)

    def test_top_k_can_be_configured_at_construction_and_query_time(self) -> None:
        question = "employee policy leave PTO benefits"
        retriever = PolicyRetriever(self.chunks, top_k=2)
        self.assertEqual(len(retriever.retrieve(question)), 2)
        self.assertEqual(len(retriever.retrieve(question, top_k=1)), 1)

    def test_category_filter_uses_available_source_metadata(self) -> None:
        results = self.retriever.retrieve("employee work policy", category="BENEFITS")
        self.assertTrue(results)
        self.assertTrue(all(r.source_metadata.policy_category == "benefits" for r in results))

    def test_source_metadata_and_chunk_fields_are_preserved(self) -> None:
        original = self._make_chunk(
            "traceable",
            "Employees accrue 15 days of PTO each calendar year.",
            document_id="doc_trace",
            metadata=SourceMetadata(
                document_id="doc_trace",
                document_title="Official Leave Policy",
                filename="leave.md",
                policy_category="leave",
                page_number=7,
                section_header="PTO Accrual",
            ),
            page_number=7,
            section_header="PTO Accrual",
        )
        result = PolicyRetriever([original]).retrieve("How many PTO days accrue?")[0]
        self.assertIsInstance(result, RetrievedPolicyChunk)
        self.assertIs(result.chunk, original)
        self.assertEqual(result.document_id, "doc_trace")
        self.assertEqual(result.chunk_id, "traceable")
        self.assertEqual(result.policy_name, "Official Leave Policy")
        self.assertEqual(result.filename, "leave.md")
        self.assertEqual(result.section_header, "PTO Accrual")
        self.assertEqual(result.page_number, 7)
        self.assertIs(result.source_metadata, original.source_metadata)
        self.assertEqual(result.text, original.chunk_text)
        self.assertGreater(result.relevance_score, 0.0)

    def test_missing_source_fields_are_not_invented(self) -> None:
        chunk = self._make_chunk("no_source", "PTO requests need supervisor approval.")
        result = PolicyRetriever([chunk]).retrieve("Who approves PTO requests?")[0]
        self.assertEqual(result.document_id, "doc_test")
        self.assertEqual(result.chunk_id, "no_source")
        self.assertEqual(result.text, chunk.chunk_text)
        self.assertIsNone(result.source_metadata)
        self.assertIsNone(result.policy_name)
        self.assertIsNone(result.filename)
        self.assertIsNone(result.section_header)
        self.assertIsNone(result.page_number)

    def test_empty_question_returns_no_results(self) -> None:
        self.assertEqual(self.retriever.retrieve(""), [])
        self.assertEqual(self.retriever.retrieve(" \n\t "), [])

    def test_empty_chunk_collection_returns_no_results(self) -> None:
        empty_retriever = PolicyRetriever([])
        self.assertEqual(empty_retriever.retrieve("PTO leave policy"), [])
        with self.assertRaises(ValueError):
            empty_retriever.retrieve("PTO leave policy", top_k=0)

    def test_no_matching_terms_returns_no_results(self) -> None:
        self.assertEqual(self.retriever.retrieve("xylophone nebula spacecraft"), [])

    def test_invalid_top_k_values_raise_value_error(self) -> None:
        for value in (0, -1, 1.5, True):
            with self.subTest(top_k=value):
                with self.assertRaises(ValueError):
                    PolicyRetriever(self.chunks, top_k=value)
                with self.assertRaises(ValueError):
                    self.retriever.retrieve("PTO leave", top_k=value)

    def test_duplicate_and_overlapping_chunks_are_returned_deterministically(self) -> None:
        source = self._make_chunk("first", "PTO employees may carry over five unused days.")
        duplicate = self._make_chunk("second", source.chunk_text)
        retriever = PolicyRetriever([source, duplicate])
        first_results = retriever.retrieve("PTO carry over unused days", top_k=2)
        second_results = retriever.retrieve("PTO carry over unused days", top_k=2)
        self.assertEqual([r.chunk_id for r in first_results], ["first", "second"])
        self.assertEqual([r.chunk_id for r in second_results], ["first", "second"])

    def test_case_insensitive_query_handling(self) -> None:
        lower = self.retriever.retrieve("hsa contribution family", category="benefits")
        upper = self.retriever.retrieve("HSA CONTRIBUTION FAMILY", category="benefits")
        self.assertEqual([r.chunk_id for r in lower], [r.chunk_id for r in upper])
        self.assertEqual(lower[0].text, upper[0].text)

    @staticmethod
    def _make_chunk(
        chunk_id: str,
        text: str,
        *,
        document_id: str = "doc_test",
        metadata: SourceMetadata | None = None,
        page_number: int | None = None,
        section_header: str | None = None,
    ) -> PolicyChunk:
        return PolicyChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            chunk_text=text,
            chunk_order=0,
            page_number=page_number,
            section_header=section_header,
            source_metadata=metadata,
        )


if __name__ == "__main__":
    unittest.main()
