"""Tests for the HTTP API and its integration with existing RAG services."""

import json
import unittest

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.service import load_sample_policy_chunks
from backend.generation import AnswerGenerator
from backend.generation.providers import ProviderTimeoutError
from backend.retrieval import PolicyRetriever


class StaticProvider:
    """Mock generation provider that returns a claim grounded in a real chunk."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def generate(self, *, instructions: str, input: str, config: object) -> str:
        self.calls += 1
        return self.response


class TimeoutProvider:
    def generate(self, *, instructions: str, input: str, config: object) -> str:
        raise ProviderTimeoutError("mock timeout")


class BrokenRetriever:
    def retrieve(self, question: str) -> list:
        raise RuntimeError("internal detail must not leak")


class PolicyApiTests(unittest.TestCase):
    """Exercise request validation, service wiring, citations, and safe failures."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.chunks = load_sample_policy_chunks()

    def build_client(self, provider: object = None, *, retriever: object = None) -> TestClient:
        selected_retriever = retriever or PolicyRetriever(self.chunks, top_k=4)
        selected_provider = provider
        generator = AnswerGenerator(selected_provider)  # type: ignore[arg-type]
        app = create_app(
            retriever=selected_retriever,  # type: ignore[arg-type]
            answer_generator=generator,
            frontend_origins=["http://localhost:4173"],
        )
        return TestClient(app)

    def test_sample_index_preserves_source_document_ids_and_metadata(self) -> None:
        sources = {
            chunk.source_metadata.filename: chunk.source_metadata
            for chunk in self.chunks
            if chunk.source_metadata is not None
        }

        self.assertEqual(len(sources), 4)
        conduct = sources["code_of_conduct_policy.txt"]
        self.assertEqual(conduct.document_id, "doc_conduct_ethics_2026_v1")
        self.assertEqual(conduct.document_title, "Acme Global Technologies - Code of Business Conduct and Ethics")
        self.assertEqual(conduct.version, "1.2")
        self.assertEqual(conduct.effective_date, "2026-01-01")

    def grounded_provider(self, question: str) -> tuple[StaticProvider, object]:
        retriever = PolicyRetriever(self.chunks, top_k=4)
        results = retriever.retrieve(question)
        self.assertTrue(results, "the fixture question should retrieve a real sample-policy chunk")
        chunk = results[0]
        provider = StaticProvider(json.dumps({
            "sufficient_evidence": True,
            "has_conflict": False,
            "claims": [{
                "text": "The retrieved policy passage contains relevant PTO guidance.",
                "source_chunk_id": chunk.chunk_id,
                "evidence_quote": chunk.text,
            }],
        }))
        return provider, retriever

    def test_health_endpoint_reports_provider_configuration(self) -> None:
        client = self.build_client()

        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "generation_configured": False})

    def test_valid_chat_request_runs_retrieval_and_generation_with_citation(self) -> None:
        question = "What are annual PTO accrual rates?"
        provider, retriever = self.grounded_provider(question)
        client = self.build_client(provider, retriever=retriever)
        expected = retriever.retrieve(question)[0]

        response = client.post("/api/chat", json={"question": question})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "generated")
        self.assertFalse(payload["abstained"])
        self.assertIn("PTO guidance", payload["answer"])
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(payload["citations"]), 1)
        citation = payload["citations"][0]
        self.assertEqual(citation["document"], "leave_policy.md")
        self.assertEqual(citation["document_id"], expected.document_id)
        self.assertEqual(citation["chunk_id"], expected.chunk_id)
        self.assertEqual(citation["section"], expected.section_header)
        self.assertEqual(citation["quote"], expected.text)
        self.assertIsNone(citation["page_number"])

    def test_empty_whitespace_and_missing_questions_are_rejected(self) -> None:
        client = self.build_client()

        for body in ({"question": ""}, {"question": "   "}, {}):
            with self.subTest(body=body):
                self.assertEqual(client.post("/api/chat", json=body).status_code, 422)

    def test_non_string_and_oversized_questions_are_rejected(self) -> None:
        client = self.build_client()

        self.assertEqual(client.post("/api/chat", json={"question": 42}).status_code, 422)
        self.assertEqual(
            client.post("/api/chat", json={"question": "x" * 2001}).status_code,
            422,
        )

    def test_no_matching_evidence_returns_abstention(self) -> None:
        provider = StaticProvider("must not be called")
        client = self.build_client(provider)

        response = client.post(
            "/api/chat",
            json={"question": "zzzxqv volcano spaceship"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["abstained"])
        self.assertEqual(payload["status"], "abstained")
        self.assertIn("couldn't find enough information", payload["answer"])
        self.assertEqual(payload["citations"], [])
        self.assertEqual(provider.calls, 0)

    def test_missing_api_key_returns_clear_configuration_error(self) -> None:
        client = self.build_client()

        response = client.post("/api/chat", json={"question": "What are annual PTO accrual rates?"})

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertTrue(payload["abstained"])
        self.assertEqual(payload["status"], "not_configured")
        self.assertEqual(payload["error"], "live_generation_not_configured")
        self.assertIn("OPENAI_API_KEY", payload["answer"])
        self.assertEqual(payload["citations"], [])

    def test_provider_timeout_returns_safe_gateway_error(self) -> None:
        client = self.build_client(TimeoutProvider())

        response = client.post("/api/chat", json={"question": "What are annual PTO accrual rates?"})

        self.assertEqual(response.status_code, 502)
        payload = response.json()
        self.assertEqual(payload["status"], "provider_error")
        self.assertEqual(payload["error"], "provider_error")
        self.assertNotIn("mock timeout", response.text)
        self.assertEqual(payload["citations"], [])

    def test_malformed_provider_response_returns_safe_gateway_error(self) -> None:
        client = self.build_client(StaticProvider("not json"))

        response = client.post("/api/chat", json={"question": "What are annual PTO accrual rates?"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["status"], "invalid_response")
        self.assertEqual(response.json()["citations"], [])

    def test_unexpected_internal_errors_are_redacted(self) -> None:
        client = self.build_client(retriever=BrokenRetriever())

        with self.assertLogs("backend.api.app", level="ERROR"):
            response = client.post("/api/chat", json={"question": "What are annual PTO accrual rates?"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["error"], "internal_error")
        self.assertNotIn("internal detail must not leak", response.text)

    def test_cors_allows_configured_frontend_origin(self) -> None:
        client = self.build_client()

        response = client.options(
            "/api/chat",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:4173")


if __name__ == "__main__":
    unittest.main()
