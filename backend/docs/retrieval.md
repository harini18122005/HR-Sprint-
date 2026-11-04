# Policy Retrieval

The retrieval service ranks `PolicyChunk` objects already produced by the ingestion and chunking pipeline. It returns matching source passages and their metadata; it does not generate an answer or infer policy facts.

## Ranking

The default `BM25RankingStrategy` is a deterministic lexical baseline. It case-folds text and tokenizes Unicode word sequences, then scores each chunk using BM25:

```text
score(question, chunk) = sum over matching query terms of
  IDF(term) * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * chunk_length / average_length))

IDF(term) = ln(1 + (N - df + 0.5) / (df + 0.5))
```

Here, `tf` is the term count in the chunk, `df` is the number of chunks containing the term, and `N` is the chunk count. The defaults are `k1=1.5` and `b=0.75`. Results sort by score descending; input order breaks ties consistently. Chunks with no query term matches are omitted.

Category filtering uses `source_metadata.policy_category`. Chunks without category metadata cannot match a category filter. When no category is requested, chunks without source metadata can still be ranked by their text.

## Supplying chunks and querying

Pass chunks from the existing extractor and chunker into `PolicyRetriever`:

```python
from pathlib import Path

from backend.ingestion.chunker import chunk_policy_document
from backend.ingestion.extractor import PolicyDocumentExtractor
from backend.ingestion.service import prepare_policy_document
from backend.retrieval import PolicyRetriever

policy_path = Path("sample-policies/leave_policy.md")
document = prepare_policy_document({
    "document_id": "doc_leave_2026",
    "title": "Acme Global Technologies Paid Time Off and Leave Policy",
    "filename": policy_path.name,
    "policy_category": "leave",
})
extracted = PolicyDocumentExtractor.extract(policy_path)
chunks = chunk_policy_document(extracted, document)

retriever = PolicyRetriever(chunks, top_k=3)
results = retriever.retrieve(
    "How much PTO can I carry over to next year?",
    category="leave",
)

for result in results:
    print(result.text)
    print(result.document_id, result.chunk_id, result.policy_name, result.filename)
    print(result.section_header, result.page_number, result.relevance_score)
```

`top_k` sets the maximum number of results. Set a default when constructing the retriever or override it on an individual `retrieve` call. It must be a positive integer. Empty questions, empty chunk collections, and questions without matching terms return an empty list.

## Source traceability

Each `RetrievedPolicyChunk` keeps the original `PolicyChunk` in its `chunk` field and provides its `document_id`, `chunk_id`, original `text`, `relevance_score`, and `source_metadata`. Convenience fields expose the policy title and filename from source metadata and the section header and page number from the chunk or its source metadata. Missing source values stay `None`; the retriever does not construct citations or infer names or page numbers.

## Extending the ranking strategy

`RankingStrategy` defines the method used by `PolicyRetriever`. A future dense or hybrid ranker can implement the same interface and return `RetrievedPolicyChunk` results. The current implementation only provides BM25; it does not claim semantic retrieval.

## Limitations

- Lexical ranking favors shared words. It can miss relevant passages when a question uses synonyms or different wording from the policy.
- It does not understand intent, resolve contradictions, or determine whether a policy applies to a specific employee.
- It retrieves source passages only. A later answer-generation component must ground any answer in returned text and preserve its citations.
- The ranker uses an in-memory snapshot of the supplied chunks. Recreate the retriever after updating the corpus.

## Tests

Run all suites, including retrieval tests, from the repository root:

```bash
python -m unittest discover -s backend/tests -v
python -m unittest backend.tests.test_policy_retrieval -v
```
