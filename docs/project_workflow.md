# Employee Question Workflow

This guide follows a request through the implemented static UI and FastAPI service. The browser does not call OpenAI directly.

## Startup: prepare the policy chunks

1. The API loads four checked-in fictional policies: leave/PTO, attendance, employee benefits, and code of conduct.
2. The existing ingestion pipeline validates metadata, extracts Markdown or plain text, and chunks the document while retaining section and source metadata.
3. The resulting `PolicyChunk` objects are kept in memory by the API process and supplied to `PolicyRetriever`.

## For each employee question

1. **Enter a question.** The employee types into the browser chat or selects a suggested question in `docs/index.html`.
2. **Send it to the backend.** `docs/chat.js` posts `{"question":"..."}` to `/api/chat` at the public URL generated into `docs/api-config.js`.
3. **Validate the request.** FastAPI validates that the question is a string of 1–2000 characters and rejects empty/whitespace input with HTTP 422.
4. **Retrieve evidence.** `PolicyRetriever` scores the sample chunks with deterministic lexical BM25 and returns the highest-ranked matches. A category filter is available in the Python service, but the HTTP chat request does not currently accept a category field.
5. **Generate from evidence.** `AnswerGenerator` passes the question and retrieved text to its configured provider. If OpenAI is not configured, generation stops with `not_configured`; automated tests inject mocked providers instead.
6. **Validate claims and build citations.** The generator checks provider JSON, chunk IDs, exact source quotes, and numeric/unit facts. It creates citation data from the original retrieval results, preserving document, section, chunk, and any legitimate page number.
7. **Return and render the response.** FastAPI returns the answer or an error/abstention with citation metadata. The browser displays those values and does not invent source labels or quotes.

## Insufficient evidence and failures

- If BM25 finds no matching chunks, the generator skips the provider and returns the standard abstention: “I couldn't find enough information in the available HR policies to answer this question. Please contact HR.” The API returns HTTP 200 with `status: "abstained"`, `abstained: true`, and an empty citation list.
- If matching chunks exist but `OPENAI_API_KEY` is unavailable, the API returns HTTP 503 with `status: "not_configured"`. It does not substitute a sample or mocked answer.
- Provider failures and invalid provider output return safe HTTP 502 responses. Unexpected service failures return a generic HTTP 500 response. Request validation failures return HTTP 422.
- The static frontend displays the response message or a network/configuration error and releases its input controls so the employee can retry.

## Traceability boundary

Citations identify evidence returned by retrieval. For Markdown and plain-text policies, page numbers are not available and remain `null`. The local quote and number checks improve traceability, but the project does not claim formal proof that every generated paraphrase follows from its quote. See [testing and evaluation](../backend/docs/testing_evaluation.md).
