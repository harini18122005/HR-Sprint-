"""Opt-in live check of the real OpenAI-backed chat API.

Run with ``python -m backend.scripts.live_generation_check`` only when a valid
OPENAI_API_KEY is configured. This makes five real, potentially billable API
requests and is intentionally excluded from automated test discovery.
"""

import os
import sys
import json
from typing import Any


SUPPORTED_QUESTIONS = (
    "How many PTO days can an employee carry over?",
    "What are the core working hours?",
    "What is the employer's HSA contribution for families?",
    "What should an employee do to report unethical behavior?",
)
UNSUPPORTED_QUESTION = "What is the company's policy for employees bringing pets to work?"


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY is not configured; no request was made.", file=sys.stderr)
        return 2

    try:
        from openai import OpenAI  # noqa: F401 - confirms the optional SDK is installed
    except ImportError:
        print("The OpenAI SDK is not installed. Install requirements.txt; no request was made.", file=sys.stderr)
        return 2

    try:
        from fastapi.testclient import TestClient
        from backend.api.app import create_app
        from backend.api.service import load_sample_policy_chunks
        from backend.retrieval import PolicyRetriever
    except ImportError as error:
        print(f"The backend dependencies are unavailable ({type(error).__name__}); no request was made.", file=sys.stderr)
        return 2

    chunks = load_sample_policy_chunks()
    retriever = PolicyRetriever(chunks, top_k=4)
    application = create_app(retriever=retriever)
    provider = application.state.answer_generator.provider
    client = TestClient(application)
    failures = 0

    for question in SUPPORTED_QUESTIONS:
        response = client.post("/api/chat", json={"question": question})
        if response.status_code != 200:
            failures += 1
            _report_failure(question, response, getattr(provider, "last_diagnostic", None))
            continue

        payload: dict[str, Any] = response.json()
        source_text = {result.chunk_id: result.text for result in retriever.retrieve(question)}
        citations = payload.get("citations", [])
        valid_citations = bool(citations) and all(
            citation.get("chunk_id") in source_text
            and citation.get("quote")
            and citation["quote"] in source_text[citation["chunk_id"]]
            for citation in citations
        )
        if payload.get("status") != "generated" or payload.get("abstained") or not valid_citations:
            failures += 1
            print(f"FAIL: {question} (answer or citation validation did not pass)")
            continue

        print(f"PASS: {question}")
        print(f"  {payload['answer']}")
        for citation in citations:
            section = citation.get("section") or "section unavailable"
            print(f"  Source: {citation.get('document')} — {section} ({citation.get('chunk_id')})")

    response = client.post("/api/chat", json={"question": UNSUPPORTED_QUESTION})
    if response.status_code == 200:
        payload = response.json()
        if payload.get("status") == "abstained" and payload.get("abstained") and not payload.get("citations"):
            print(f"PASS: unsupported question abstained: {UNSUPPORTED_QUESTION}")
        else:
            failures += 1
            print("FAIL: unsupported question did not safely abstain")
    else:
        failures += 1
        _report_failure(UNSUPPORTED_QUESTION, response, getattr(provider, "last_diagnostic", None))

    print(f"Live check completed: {5 - failures} passed, {failures} failed.")
    return 1 if failures else 0


def _report_failure(question: str, response: Any, diagnostic: Any = None) -> None:
    """Print sanitized API status and safe provider metadata, never key or message."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    detail = body.get("detail", {}) if isinstance(body, dict) else {}
    if not isinstance(detail, dict):
        detail = {}
    error = body.get("error") or detail.get("error") or "request_failed"
    print(f"FAIL: {question} (HTTP {response.status_code}, {error})")
    if diagnostic is not None and hasattr(diagnostic, "as_dict"):
        print("  Provider diagnostic: " + json.dumps(diagnostic.as_dict(), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
