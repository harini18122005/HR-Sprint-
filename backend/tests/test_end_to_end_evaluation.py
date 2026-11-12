"""End-to-end workflow and retrieval evaluation using mock generation only."""

import json
import unittest

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.service import load_sample_policy_chunks
from backend.generation import AnswerGenerator, GenerationStatus
from backend.retrieval import PolicyRetriever
from backend.schemas.chunk import PolicyChunk


class EvidenceEchoProvider:
    """Return a controlled claim quoting the selected retrieved passage."""

    def __init__(self, chunk_id: str, quote: str) -> None:
        self.chunk_id = chunk_id
        self.quote = quote
        self.received_input: str | None = None

    def generate(self, *, instructions: str, input: str, config: object) -> str:
        self.received_input = input
        return json.dumps({
            "sufficient_evidence": True,
            "has_conflict": False,
            "claims": [{
                "text": "Report suspected code violations to People Operations.",
                "source_chunk_id": self.chunk_id,
                "evidence_quote": self.quote,
            }],
        })


class RetrievalEvaluationTests(unittest.TestCase):
    """Check retrieval against all sample policy categories and a negative query."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.chunks = load_sample_policy_chunks()
        cls.retriever = PolicyRetriever(cls.chunks, top_k=5)

    def test_leave_question_retrieves_relevant_traceable_evidence(self) -> None:
        result = self._assert_relevant(
            "How many unused PTO days may carry into the next calendar year?",
            "leave_policy.md",
            "maximum of 5 unused PTO days",
        )
        self.assertEqual(result.source_metadata.policy_category, "leave")

    def test_attendance_question_retrieves_relevant_traceable_evidence(self) -> None:
        result = self._assert_relevant(
            "When should salaried staff be online for core collaboration hours?",
            "attendance_policy.md",
            "10:00 AM to 3:00 PM",
        )
        self.assertEqual(result.source_metadata.policy_category, "attendance")

    def test_benefits_question_retrieves_relevant_traceable_evidence(self) -> None:
        result = self._assert_relevant(
            "What annual HSA contribution is available for families?",
            "employee_benefits_policy.md",
            "$2,000 for families",
        )
        self.assertEqual(result.source_metadata.policy_category, "benefits")

    def test_code_of_conduct_question_retrieves_relevant_traceable_evidence(self) -> None:
        result = self._assert_relevant(
            "Where can an employee report a suspected code violation?",
            "code_of_conduct_policy.txt",
            "report it directly to People Operations",
        )
        self.assertEqual(result.source_metadata.policy_category, "code_of_conduct")

    def test_irrelevant_question_returns_no_misleading_policy_result(self) -> None:
        self.assertEqual(
            self.retriever.retrieve("quantum spacecraft lunar telescope"),
            [],
        )

    def _assert_relevant(self, question: str, filename: str, expected_text: str):
        results = self.retriever.retrieve(question)
        self.assertTrue(results)
        self.assertIn(expected_text, results[0].text)
        self.assertEqual(results[0].filename, filename)
        self.assertTrue(results[0].document_id)
        self.assertTrue(results[0].chunk_id)
        self.assertTrue(results[0].section_header)
        self.assertGreater(results[0].relevance_score, 0)
        return results[0]


class EndToEndWorkflowTests(unittest.TestCase):
    """Exercise question -> retrieval -> provider -> citation -> HTTP response."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.chunks = load_sample_policy_chunks()

    def test_chat_passes_retrieved_conduct_evidence_and_returns_its_citation(self) -> None:
        question = "Where can an employee report a suspected code violation?"
        retriever = PolicyRetriever(self.chunks, top_k=5)
        retrieved = retriever.retrieve(question)
        self.assertTrue(retrieved)
        selected = next(
            result for result in retrieved
            if "report it directly to People Operations" in result.text
        )
        quote = "report it directly to People Operations"
        provider = EvidenceEchoProvider(selected.chunk_id, quote)
        app = create_app(
            retriever=retriever,
            answer_generator=AnswerGenerator(provider),
            frontend_origins=["http://localhost:4173"],
        )

        response = TestClient(app).post("/api/chat", json={"question": question})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload), {"answer", "citations", "abstained", "status", "error"}
        )
        self.assertEqual(payload["status"], "generated")
        self.assertFalse(payload["abstained"])
        self.assertIn("People Operations", payload["answer"])
        self.assertEqual(len(payload["citations"]), 1)
        citation = payload["citations"][0]
        self.assertEqual(citation["document"], "code_of_conduct_policy.txt")
        self.assertEqual(citation["document_id"], selected.document_id)
        self.assertEqual(citation["chunk_id"], selected.chunk_id)
        self.assertEqual(citation["section"], selected.section_header)
        self.assertEqual(citation["quote"], quote)
        self.assertIsNone(citation["page_number"])

        # Confirm the provider context came from this retriever result, not a fixture answer.
        provider_input = json.loads(provider.received_input)
        self.assertEqual(provider_input["question"], question)
        evidence = provider_input["retrieved_policy_evidence"]
        self.assertTrue(any(
            item["chunk_id"] == selected.chunk_id and item["text"] == selected.text
            for item in evidence
        ))

    def test_unverifiable_citation_quote_and_number_are_rejected(self) -> None:
        text = "Employees may carry over a maximum of 5 unused PTO days."
        chunk = PolicyChunk(
            chunk_id="evaluation-pto",
            document_id="evaluation-leave",
            chunk_text=text,
            chunk_order=0,
        )
        result = PolicyRetriever([chunk]).retrieve("PTO carry over days")[0]
        invalid_claims = (
            # Unknown citation ID, even though the quote happens to be real.
            {"text": "The limit is 5 days.", "source_chunk_id": "missing", "evidence_quote": "5 unused PTO days"},
            # A quote must match the original chunk exactly.
            {"text": "The limit is 5 days.", "source_chunk_id": result.chunk_id, "evidence_quote": "up to 5 PTO days"},
            # Numeric policy claims must be present in that exact evidence quote.
            {"text": "Employees receive 15 PTO days annually.", "source_chunk_id": result.chunk_id, "evidence_quote": "5 unused PTO days"},
        )

        for claim in invalid_claims:
            with self.subTest(claim=claim):
                response = json.dumps({
                    "sufficient_evidence": True,
                    "has_conflict": False,
                    "claims": [claim],
                })

                class InvalidProvider:
                    def generate(self, *, instructions: str, input: str, config: object) -> str:
                        return response

                generated = AnswerGenerator(InvalidProvider()).generate(
                    "How many PTO days?", [result]
                )
                self.assertEqual(generated.status, GenerationStatus.INVALID_RESPONSE)
                self.assertEqual(generated.citations, ())
                self.assertNotIn("15 PTO days", generated.answer)


if __name__ == "__main__":
    unittest.main()
