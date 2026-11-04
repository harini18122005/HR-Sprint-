"""Deterministic lexical retrieval for source-grounded HR policy chunks.

This module provides a BM25 baseline over existing ``PolicyChunk`` objects. It
does not perform semantic search or generate answers.
"""

from collections import Counter
from dataclasses import dataclass
import math
import re
from typing import Iterable, List, Optional, Protocol, Sequence, Tuple

from backend.schemas.chunk import PolicyChunk, SourceMetadata


_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    """Return lowercase alphanumeric word tokens, including Unicode letters."""
    return _TOKEN_PATTERN.findall(text.casefold())


def _category_value(category: object) -> str:
    """Normalize a category string or string-valued enum for comparison."""
    value = getattr(category, "value", category)
    return str(value).strip().casefold()


def _validate_top_k(top_k: int) -> None:
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("top_k must be a positive integer.")


@dataclass(frozen=True)
class RetrievedPolicyChunk:
    """A ranked result that retains its original chunk and provenance unchanged."""

    chunk: PolicyChunk
    relevance_score: float

    @property
    def document_id(self) -> str:
        return self.chunk.document_id

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    @property
    def text(self) -> str:
        return self.chunk.chunk_text

    @property
    def source_metadata(self) -> Optional[SourceMetadata]:
        return self.chunk.source_metadata

    @property
    def policy_name(self) -> Optional[str]:
        source = self.chunk.source_metadata
        return source.document_title if source else None

    @property
    def filename(self) -> Optional[str]:
        source = self.chunk.source_metadata
        return source.filename if source else None

    @property
    def section_header(self) -> Optional[str]:
        source = self.chunk.source_metadata
        return self.chunk.section_header or (source.section_header if source else None)

    @property
    def page_number(self) -> Optional[int]:
        source = self.chunk.source_metadata
        return self.chunk.page_number or (source.page_number if source else None)


class RankingStrategy(Protocol):
    """Interface for interchangeable lexical or future dense ranking strategies."""

    def rank(
        self,
        question: str,
        *,
        top_k: int,
        category: Optional[str] = None,
    ) -> List[RetrievedPolicyChunk]:
        """Rank indexed policy chunks for a question."""


class BM25RankingStrategy:
    """BM25 lexical ranker with corpus statistics built from supplied chunks."""

    def __init__(
        self,
        chunks: Sequence[PolicyChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive.")
        if not 0.0 <= b <= 1.0:
            raise ValueError("b must be between 0 and 1 inclusive.")

        self._chunks = tuple(chunks)
        self._k1 = k1
        self._b = b
        self._term_counts: Tuple[Counter[str], ...] = tuple(
            Counter(_tokenize(chunk.chunk_text)) for chunk in self._chunks
        )
        self._lengths = tuple(sum(counts.values()) for counts in self._term_counts)
        self._average_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )

        document_frequency: Counter[str] = Counter()
        for counts in self._term_counts:
            document_frequency.update(counts.keys())
        document_count = len(self._chunks)
        self._inverse_document_frequency = {
            term: math.log(1.0 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def rank(
        self,
        question: str,
        *,
        top_k: int,
        category: Optional[str] = None,
    ) -> List[RetrievedPolicyChunk]:
        query_terms = set(_tokenize(question))
        if not query_terms or not self._chunks:
            return []

        normalized_category = _category_value(category) if category is not None else None
        ranked: List[Tuple[float, int, PolicyChunk]] = []

        for index, chunk in enumerate(self._chunks):
            if normalized_category is not None:
                source = chunk.source_metadata
                if source is None or not source.policy_category:
                    continue
                if _category_value(source.policy_category) != normalized_category:
                    continue

            counts = self._term_counts[index]
            length = self._lengths[index]
            score = 0.0
            for term in sorted(query_terms):
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                idf = self._inverse_document_frequency[term]
                if self._average_length:
                    length_norm = 1.0 - self._b + self._b * length / self._average_length
                else:
                    length_norm = 1.0
                denominator = frequency + self._k1 * length_norm
                score += idf * (frequency * (self._k1 + 1.0)) / denominator

            if score > 0.0:
                ranked.append((score, index, chunk))

        # Original input order is the deterministic tie-breaker.
        ranked.sort(key=lambda result: (-result[0], result[1]))
        return [
            RetrievedPolicyChunk(chunk=chunk, relevance_score=score)
            for score, _, chunk in ranked[:top_k]
        ]


class PolicyRetriever:
    """Retrieve relevant policy chunks using an interchangeable ranking strategy.

    Args:
        chunks: Existing chunks from the Day 4 ingestion and chunking pipeline.
        top_k: Default maximum number of results returned by :meth:`retrieve`.
        ranking_strategy: Optional strategy replacement; BM25 is used by default.
    """

    def __init__(
        self,
        chunks: Iterable[PolicyChunk],
        *,
        top_k: int = 5,
        ranking_strategy: Optional[RankingStrategy] = None,
    ) -> None:
        _validate_top_k(top_k)
        self._chunks = tuple(chunks)
        self.top_k = top_k
        self._ranking_strategy = ranking_strategy or BM25RankingStrategy(self._chunks)

    def retrieve(
        self,
        question: str,
        *,
        top_k: Optional[int] = None,
        category: Optional[str] = None,
    ) -> List[RetrievedPolicyChunk]:
        """Return matching chunks ranked by relevance, with source provenance.

        Empty or whitespace-only questions return no results. Questions with no
        lexical matches also return an empty list.
        """
        if not isinstance(question, str):
            raise TypeError("question must be a string.")
        result_limit = self.top_k if top_k is None else top_k
        _validate_top_k(result_limit)
        if category is not None and not _category_value(category):
            raise ValueError("category must be a non-empty string when provided.")
        if not question.strip() or not self._chunks:
            return []

        return self._ranking_strategy.rank(
            question,
            top_k=result_limit,
            category=_category_value(category) if category is not None else None,
        )
