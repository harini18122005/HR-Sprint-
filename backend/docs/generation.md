# RAG Answer Generation

The answer-generation service consumes results from the Day 5 `PolicyRetriever`. It does not retrieve documents itself or make a claim that was not returned as a cited claim by the provider. No frontend or API endpoint is part of this milestone.

## Flow

1. The caller passes an employee question and the retrieved `RetrievedPolicyChunk` results to `AnswerGenerator.generate`.
2. The prompt builder serializes each result's chunk ID, document ID, title, filename, section, page (when supplied), and original text as JSON evidence.
3. Developer instructions treat that JSON as untrusted reference data, so instructions found inside a policy passage cannot change model behavior.
4. The provider returns structured claims. Each claim must name a supplied chunk and include an exact quote from that chunk.
5. The service validates the JSON, source IDs, quotes, and numeric facts, then creates citation objects and inline references from the original retrieval results.

If there are no retrieved results, generation is skipped and the service returns:

> I couldn't find enough information in the available HR policies to answer this question. Please contact HR.

The same abstention is returned when the provider says evidence is insufficient. When evidence conflicts, the result marks `has_conflict` and reports separately cited claims from the conflicting passages. Missing source metadata stays `None`; the service does not invent policy titles, sections, or pages.

## Usage

The following example shows the service call shape; it makes a live API request only when a configured provider is supplied and `generate` is called.

```python
from backend.generation import AnswerGenerator, OpenAIResponsesProvider
from backend.retrieval import PolicyRetriever

question = "How many PTO days can I carry over?"
retrieved = PolicyRetriever(policy_chunks, top_k=3).retrieve(question, category="leave")
provider = OpenAIResponsesProvider.from_environment()
result = AnswerGenerator(provider).generate(question, retrieved)

print(result.status.value)
print(result.answer)
for citation in result.citations:
    print(citation.source_label, citation.chunk_id, citation.section_header, citation.page_number)
```

`AnswerGenerationResult` contains the question, answer, citation tuple, `sufficient_evidence`, status, and a conflict flag. `sufficient_evidence` is `None` when generation could not assess the evidence because the provider was not configured or failed.

## OpenAI provider configuration

The optional live provider uses the official OpenAI Python SDK and the Responses API. The SDK is imported lazily; tests and unconfigured installations do not need to import it. See the [official text generation guide](https://developers.openai.com/api/docs/guides/text?lang=python) and [official Python SDK setup](https://developers.openai.com/api/docs/libraries).

Install the dependency:

```bash
python -m pip install -r requirements.txt
```

Set these variables in the process environment or your deployment configuration:

- `OPENAI_API_KEY`: Required for live generation. Never commit a real key.
- `OPENAI_MODEL`: Optional model override. The default is `gpt-6-astra`.

`.env.example` contains placeholders only. The application reads environment variables directly and does not load `.env` files automatically. If the API key is missing, the result status is `not_configured`, and no live answer is claimed.

`GenerationConfig` controls model, maximum output tokens, and request timeout. Provider retries are disabled so timeouts and errors return a safe status instead of issuing repeat calls.

## Grounding checks and limitations

- Every returned factual claim has a locally generated citation to a retrieved chunk. Provider-supplied IDs must match results returned by Day 5 retrieval.
- Evidence quotes must appear exactly in their cited chunk. Numeric values, currency/percentage markers, and HR units in a claim must also appear in that quote; otherwise the entire provider response is rejected and no generated claim is shown.
- These checks catch invalid sources, fabricated quotes, and unsupported numeric values. They do not prove full natural-language entailment, so HR policy changes should be tested against reviewed examples before production use.
- The prompt explicitly treats document content as data, not instructions. Prompting and source validation reduce risk but cannot guarantee that every model interpretation is correct.
- Provider errors, timeouts, and malformed responses return safe statuses with no model text or citations shown.
- Live API behavior was not used by automated tests. The tests use mock providers and make no paid calls.

## Tests

```bash
python -m unittest backend.tests.test_answer_generation -v
python -m unittest discover -s backend/tests -v
```
