# Testing and Evaluation

PeopleDesk AI's tests check the pipeline from sample policy ingestion through HTTP response handling. Tests use checked-in fictional sample policies, controlled inputs, and mocked generation providers. They do not send requests to OpenAI and do not prove that live OpenAI generation, credentials, or network connectivity work.

## Run the suites

From the repository root:

```bash
python -m unittest discover -s backend/tests -v
node --test frontend/tests/chat.test.cjs
python -m unittest frontend.tests.test_build_config -v
```

The backend command includes unit tests for schema validation, extraction, chunking, BM25 retrieval, answer validation, API behavior, and the Day 9 end-to-end/evaluation cases. Node's built-in test runner exercises the static chat interactions; the final Python command checks the frontend's public API URL configuration generator. No additional test dependency is required beyond the project requirements.

## What is covered

- **Complete chat workflow:** a question is submitted to `POST /api/chat`, BM25 retrieves actual checked-in sample-policy chunks, the mocked provider receives those chunks, generated claims are validated against chunk IDs and exact quotes, and the HTTP response returns the answer and source citation.
- **Retrieval evaluation:** leave/PTO, attendance/core hours, benefits/HSA, and code-of-conduct questions are checked against the expected policy text and source metadata. A deliberately unrelated query must return no results.
- **Grounding and citations:** tests reject unknown chunk IDs, quotes absent from the cited chunk, unsupported numbers or policy units, malformed provider output, and uncited claims. Conflicting evidence is surfaced, and insufficient evidence produces an abstention.
- **HTTP API:** tests cover `GET /api/health`, successful chat, empty and whitespace questions, missing or invalid request fields, malformed input, no matching evidence, missing provider configuration, provider timeouts/errors, malformed provider output, retrieval failures, and unexpected errors. Safe responses must not disclose internal exception details.
- **Existing functionality:** schema validation, source metadata, extraction, chunking, retriever ranking, answer generation, and browser interaction suites continue to run as part of the listed commands.

## Mocked versus live behavior

Mock providers return deterministic JSON for tests. This verifies application wiring, response validation, citations, abstention, and error handling without paid API calls. A passing mocked suite does **not** establish that a live model will follow the prompt, that the OpenAI API key is valid, or that a live response will be available. The test suite intentionally does not configure a real key or make paid API calls.

## Known limitations

- Retrieval is lexical BM25. It may miss passages expressed with different terminology and is evaluated only against the small checked-in sample corpus.
- Citation checks prove that each accepted claim supplies a real retrieved chunk ID and an exact quote, and guard numeric values and common policy units. They do not prove that every possible natural-language paraphrase is logically entailed by its quote.
- Conflict tests verify that separately sourced conflicting claims are explicitly marked. The system does not determine which policy version takes precedence.
- API integration tests use FastAPI's in-process test client. They do not test production hosting, browser-to-deployed-server networking, CORS deployment configuration, or live model calls.

For detailed behavior see [the retrieval guide](retrieval.md), [the generation guide](generation.md), and [the API guide](api.md).
