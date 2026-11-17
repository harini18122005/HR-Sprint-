# Mentor Demo Guide (6 minutes)

This plan uses the application as implemented: a static browser interface connected to a local FastAPI backend. It does not assume that the backend is deployed or that live AI credentials are configured.

## Before the demo

1. Follow [the setup guide](setup_guide.md) to start Uvicorn and serve the `docs/` page locally.
2. Check `http://127.0.0.1:8000/api/health`. Record whether `generation_configured` is `true` or `false` before presenting.
3. If there is no approved API key, keep it that way. Explain that evidence-backed questions receive an explicit not-configured response; use the mocked automated tests to demonstrate the generation flow. Do not present a mock test response as a live model answer.
4. Keep this demo on fictional sample policies. No genuine screenshots were present in the repository when this guide was prepared.

## Run of show

| Time | What to show and say |
|---|---|
| 0:00–0:40 | **Introduction.** “PeopleDesk AI helps employees find answers in HR policy documents and shows which policy passages support a generated answer.” Explain that the included Acme policies are fictional. |
| 0:40–1:15 | **Problem.** Policy documents can be long, and a general chatbot may invent rules. This prototype retrieves policy evidence and checks source IDs and quotes before returning a generated answer. |
| 1:15–2:00 | **Architecture.** Show [architecture.md](architecture.md): static HTML/CSS/JavaScript UI → FastAPI → policy extraction/chunking and BM25 → optional provider → validated citations. Clarify that there is no React app, vector database, or deployed API. |
| 2:00–3:30 | **UI and questions.** Show the responsive chat page. Try “How many unused PTO days can carry over?”, “When are core collaboration hours?”, or “What HSA contribution is available for families?” The page sends requests to the backend. With live generation configured, answers should include the source filename, section/chunk, and exact quote. Without a key, show the explicit not-configured response rather than implying a live answer. |
| 3:30–4:10 | **Insufficient evidence.** Ask an unrelated question such as “What is the lunar spacecraft schedule?” The lexical retriever should find no matching sample policy and return the abstention message with no citations. This path does not require a model call. |
| 4:10–5:05 | **Source traceability.** Explain how document and chunk IDs and exact quoted text are preserved. The Markdown/text examples do not have page numbers, so the UI does not invent them. Mention that citation checks reduce unsupported claims but do not prove every paraphrase. |
| 5:05–5:40 | **Tests.** Run the commands below or show their recorded local results: 87 backend tests, 7 frontend interaction tests, and 5 frontend configuration tests passed (99 total) in the Day 10 verification. The provider is mocked in automated tests; no paid calls are made. |
| 5:40–6:00 | **Limitations and next steps.** BM25 is lexical and uses four fictional sample files; there is no database, policy upload/admin flow, authentication, production monitoring, or deployed backend. Future work could evaluate hybrid retrieval, add reviewed policies and versioning, and harden deployment/access controls. |

## Test commands

From the repository root:

```powershell
python -m unittest discover -s backend/tests -v
node --test frontend/tests/chat.test.cjs
python -m unittest frontend.tests.test_build_config -v
```

The Day 10 verification run completed with 87 backend tests, 7 frontend interaction tests, and 5 frontend configuration tests passing. Tests with mocked providers verify application wiring and safety checks, not live OpenAI availability or output quality.

## Distinguish the four demo states

- **Static UI:** the browser page is a local static HTML/CSS/JavaScript app. The UI is not itself an AI model.
- **Backend integration:** the page sends a real HTTP request to the local FastAPI API. This does not mean that the API is deployed publicly.
- **Mocked tests:** test-only providers return controlled JSON so retrieval, validation, citations, abstention, and API behavior can be verified without external calls.
- **Live AI:** only call a response live if the backend health endpoint reports generation configured and the request succeeds against the configured provider during the demo. No key is included in this repository; live generation was not exercised in the automated tests.
