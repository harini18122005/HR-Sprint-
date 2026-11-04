"""Source-grounded answer generation from Day 5 retrieved policy results."""

from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import List, Optional, Sequence, Tuple

from backend.generation.prompts import SYSTEM_INSTRUCTIONS, build_generation_input
from backend.generation.providers import (
    GenerationConfig,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderTimeoutError,
    TextGenerationProvider,
)
from backend.retrieval.retriever import RetrievedPolicyChunk


ABSTENTION_MESSAGE = (
    "I couldn't find enough information in the available HR policies to answer "
    "this question. Please contact HR."
)
NOT_CONFIGURED_MESSAGE = (
    "Live answer generation is not configured. Set OPENAI_API_KEY and install "
    "the OpenAI SDK to enable it; no live answer was generated."
)
GENERATION_ERROR_MESSAGE = (
    "I couldn't generate a verified answer right now. Please try again later or contact HR."
)
INVALID_QUESTION_MESSAGE = "Please enter a question about an HR policy."
_INLINE_CITATION_PATTERN = re.compile(r"\[[^\]]+\]")
_NUMBER_PATTERN = re.compile(
    r"(?<!\w)(\$?)(\d[\d,]*(?:\.\d+)?)(%?)(?!\w)",
    re.IGNORECASE,
)
_UNIT_PATTERN = re.compile(
    r"\b(business\s+days?|calendar\s+years?|days?|hours?|weeks?|months?|years?|"
    r"percent(?:age)?|dollars?|annually|annual|monthly|weekly|daily)\b",
    re.IGNORECASE,
)


def _number_facts(text: str) -> set[tuple[str, str]]:
    """Extract literal numeric values and currency/percentage markers."""
    facts: set[tuple[str, str]] = set()
    for match in _NUMBER_PATTERN.finditer(text):
        value = match.group(2).replace(",", "")
        marker = "currency" if match.group(1) else "percent" if match.group(3) else ""
        facts.add((value, marker))
    return facts


def _unit_facts(text: str) -> set[str]:
    """Extract HR-relevant units so a quote cannot support a changed unit."""
    units = set()
    for match in _UNIT_PATTERN.finditer(text):
        value = " ".join(match.group(1).casefold().split())
        if value.endswith("s"):
            value = value[:-1]
        units.add(value)
    return units


class GenerationStatus(str, Enum):
    """Outcome of an answer-generation request."""

    GENERATED = "generated"
    ABSTAINED = "abstained"
    NOT_CONFIGURED = "not_configured"
    PROVIDER_ERROR = "provider_error"
    INVALID_RESPONSE = "invalid_response"
    INVALID_QUESTION = "invalid_question"


@dataclass(frozen=True)
class AnswerCitation:
    """A source citation built from a retrieved result, never model-invented."""

    citation_number: int
    document_id: str
    chunk_id: str
    document_title: Optional[str]
    filename: Optional[str]
    section_header: Optional[str]
    page_number: Optional[int]
    evidence_quote: str

    @property
    def source_label(self) -> str:
        return self.document_title or self.filename or f"Document ID {self.document_id}"


@dataclass(frozen=True)
class AnswerGenerationResult:
    """Structured response with the question, answer, sources, and evidence state."""

    question: str
    answer: str
    citations: Tuple[AnswerCitation, ...]
    sufficient_evidence: Optional[bool]
    status: GenerationStatus
    has_conflict: bool = False


class _InvalidProviderResponse(ValueError):
    """Internal signal for malformed or ungrounded provider output."""


class AnswerGenerator:
    """Generate concise answers using only retrieved policy evidence.

    The provider must return structured claims with a chunk ID and an exact
    supporting quote for every claim. The service validates those references,
    then creates citations locally from the original retrieval results.
    """

    def __init__(
        self,
        provider: Optional[TextGenerationProvider],
        config: Optional[GenerationConfig] = None,
    ) -> None:
        self.provider = provider
        self.config = config or GenerationConfig()

    def generate(
        self,
        question: str,
        retrieved_results: Sequence[RetrievedPolicyChunk],
    ) -> AnswerGenerationResult:
        """Generate an answer from results returned by ``PolicyRetriever``."""
        if not isinstance(question, str) or not question.strip():
            return AnswerGenerationResult(
                question=question if isinstance(question, str) else "",
                answer=INVALID_QUESTION_MESSAGE,
                citations=(),
                sufficient_evidence=False,
                status=GenerationStatus.INVALID_QUESTION,
            )

        results = tuple(retrieved_results)
        if not results:
            return self._abstain(question)

        if self.provider is None:
            return self._unavailable(question)

        try:
            raw_response = self.provider.generate(
                instructions=SYSTEM_INSTRUCTIONS,
                input=build_generation_input(question, results),
                config=self.config,
            )
        except ProviderNotConfiguredError:
            return self._unavailable(question)
        except (ProviderTimeoutError, TimeoutError):
            return self._provider_failure(question)
        except Exception:
            return self._provider_failure(question)

        try:
            sufficient, has_conflict, claims = self._parse_response(raw_response, results)
        except _InvalidProviderResponse:
            return AnswerGenerationResult(
                question=question,
                answer=GENERATION_ERROR_MESSAGE,
                citations=(),
                sufficient_evidence=None,
                status=GenerationStatus.INVALID_RESPONSE,
            )

        if not sufficient:
            return self._abstain(question)

        citations_by_chunk: dict[str, AnswerCitation] = {}
        rendered_claims: List[str] = []
        for claim_text, chunk_id, quote, result in claims:
            citation = citations_by_chunk.get(chunk_id)
            if citation is None:
                citation = AnswerCitation(
                    citation_number=len(citations_by_chunk) + 1,
                    document_id=result.document_id,
                    chunk_id=result.chunk_id,
                    document_title=result.policy_name,
                    filename=result.filename,
                    section_header=result.section_header,
                    page_number=result.page_number,
                    evidence_quote=quote,
                )
                citations_by_chunk[chunk_id] = citation
            rendered_claims.append(f"{claim_text} [{citation.citation_number}]")

        answer_body = "\n".join(f"- {claim}" for claim in rendered_claims)
        if has_conflict:
            answer_body = "The retrieved policy passages conflict:\n" + answer_body

        return AnswerGenerationResult(
            question=question,
            answer=answer_body,
            citations=tuple(citations_by_chunk.values()),
            sufficient_evidence=True,
            status=GenerationStatus.GENERATED,
            has_conflict=has_conflict,
        )

    @staticmethod
    def _parse_response(
        raw_response: str,
        results: Sequence[RetrievedPolicyChunk],
    ) -> Tuple[bool, bool, List[Tuple[str, str, str, RetrievedPolicyChunk]]]:
        try:
            payload = json.loads(raw_response)
        except (TypeError, json.JSONDecodeError) as error:
            raise _InvalidProviderResponse("Provider response was not valid JSON.") from error

        if not isinstance(payload, dict):
            raise _InvalidProviderResponse("Provider response must be a JSON object.")
        sufficient = payload.get("sufficient_evidence")
        has_conflict = payload.get("has_conflict")
        raw_claims = payload.get("claims")
        if not isinstance(sufficient, bool) or not isinstance(has_conflict, bool):
            raise _InvalidProviderResponse("Evidence and conflict flags must be booleans.")
        if not isinstance(raw_claims, list):
            raise _InvalidProviderResponse("claims must be a list.")
        if not sufficient:
            if raw_claims or has_conflict:
                raise _InvalidProviderResponse("Abstentions cannot contain claims or conflicts.")
            return False, False, []
        if not raw_claims:
            raise _InvalidProviderResponse("A sufficient answer must contain cited claims.")

        result_by_chunk: dict[str, RetrievedPolicyChunk] = {}
        for result in results:
            result_by_chunk.setdefault(result.chunk_id, result)

        claims: List[Tuple[str, str, str, RetrievedPolicyChunk]] = []
        for raw_claim in raw_claims:
            if not isinstance(raw_claim, dict):
                raise _InvalidProviderResponse("Each claim must be an object.")
            text = raw_claim.get("text")
            chunk_id = raw_claim.get("source_chunk_id")
            quote = raw_claim.get("evidence_quote")
            if not all(isinstance(value, str) and value.strip() for value in (text, chunk_id, quote)):
                raise _InvalidProviderResponse("Claims need text, a source chunk ID, and an evidence quote.")
            if _INLINE_CITATION_PATTERN.search(text):
                raise _InvalidProviderResponse("Claims must not provide their own citations.")
            result = result_by_chunk.get(chunk_id)
            if result is None:
                raise _InvalidProviderResponse("Claim refers to a chunk outside the retrieved evidence.")
            if quote not in result.text:
                raise _InvalidProviderResponse("Evidence quote is not an exact passage from its source chunk.")
            quoted_facts = _number_facts(quote)
            if not _number_facts(text).issubset(quoted_facts):
                raise _InvalidProviderResponse(
                    "Claim introduces a numeric policy fact absent from its evidence quote."
                )
            if not _unit_facts(text).issubset(_unit_facts(quote)):
                raise _InvalidProviderResponse(
                    "Claim introduces a policy unit absent from its evidence quote."
                )
            claims.append((text.strip(), chunk_id, quote, result))

        if has_conflict and len({claim[1] for claim in claims}) < 2:
            raise _InvalidProviderResponse("A conflict needs claims from at least two distinct chunks.")
        return True, has_conflict, claims

    @staticmethod
    def _abstain(question: str) -> AnswerGenerationResult:
        return AnswerGenerationResult(
            question=question,
            answer=ABSTENTION_MESSAGE,
            citations=(),
            sufficient_evidence=False,
            status=GenerationStatus.ABSTAINED,
        )

    @staticmethod
    def _unavailable(question: str) -> AnswerGenerationResult:
        return AnswerGenerationResult(
            question=question,
            answer=NOT_CONFIGURED_MESSAGE,
            citations=(),
            sufficient_evidence=None,
            status=GenerationStatus.NOT_CONFIGURED,
        )

    @staticmethod
    def _provider_failure(question: str) -> AnswerGenerationResult:
        return AnswerGenerationResult(
            question=question,
            answer=GENERATION_ERROR_MESSAGE,
            citations=(),
            sufficient_evidence=None,
            status=GenerationStatus.PROVIDER_ERROR,
        )
