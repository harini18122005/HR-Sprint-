"""FastAPI application that exposes the existing retrieval and generation services."""

import logging
import os
from typing import Optional, Sequence

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.api.service import load_sample_policy_chunks
from backend.generation import (
    AnswerGenerationResult,
    AnswerGenerator,
    GenerationStatus,
    OpenAIResponsesProvider,
)
from backend.retrieval import PolicyRetriever


logger = logging.getLogger(__name__)
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)
_MAX_QUESTION_LENGTH = 2000


class ChatRequest(BaseModel):
    """Validated employee question payload."""

    question: str = Field(min_length=1, max_length=_MAX_QUESTION_LENGTH)


class CitationResponse(BaseModel):
    """Traceable source details for one evidence-backed claim."""

    document: str
    document_id: str
    section: Optional[str] = None
    chunk_id: str
    quote: str
    page_number: Optional[int] = None


class ChatResponse(BaseModel):
    """Stable response shape shared by successful, abstained, and error results."""

    answer: str
    citations: list[CitationResponse]
    abstained: bool
    status: str
    error: Optional[str] = None


def _parse_origins(raw_origins: Optional[str] = None) -> list[str]:
    """Read explicit browser origins; default to the documented local UI ports."""
    value = os.environ.get("FRONTEND_ORIGINS") if raw_origins is None else raw_origins
    if value is None:
        return list(_DEFAULT_CORS_ORIGINS)
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


def _to_chat_response(result: AnswerGenerationResult, error: Optional[str] = None) -> ChatResponse:
    citations = [
        CitationResponse(
            document=citation.filename or citation.document_title or citation.document_id,
            document_id=citation.document_id,
            section=citation.section_header,
            chunk_id=citation.chunk_id,
            quote=citation.evidence_quote,
            page_number=citation.page_number,
        )
        for citation in result.citations
    ]
    return ChatResponse(
        answer=result.answer,
        citations=citations,
        abstained=result.sufficient_evidence is not True,
        status=result.status.value,
        error=error,
    )


def create_app(
    *,
    retriever: Optional[PolicyRetriever] = None,
    answer_generator: Optional[AnswerGenerator] = None,
    frontend_origins: Optional[Sequence[str]] = None,
) -> FastAPI:
    """Create an API app, with injectable services for isolated tests."""
    selected_retriever = retriever or PolicyRetriever(load_sample_policy_chunks())
    selected_generator = answer_generator or AnswerGenerator(
        OpenAIResponsesProvider.from_environment()
    )

    application = FastAPI(
        title="PeopleDesk AI Policy API",
        version="1.0.0",
        description="Source-grounded answers from the checked-in sample HR policies.",
    )
    application.state.policy_retriever = selected_retriever
    application.state.answer_generator = selected_generator

    origins = list(frontend_origins) if frontend_origins is not None else _parse_origins()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.get("/api/health")
    def health() -> dict[str, object]:
        provider = selected_generator.provider
        configured = bool(getattr(provider, "is_configured", provider is not None))
        return {"status": "ok", "generation_configured": configured}

    @application.post("/api/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse | JSONResponse:
        question = request.question.strip()
        if not question:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_question", "answer": "Please enter a question about an HR policy."},
            )

        try:
            results = selected_retriever.retrieve(question)
            result = selected_generator.generate(question, results)
        except Exception:
            logger.exception("Policy chat request failed unexpectedly")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "internal_error",
                    "answer": "The policy service is temporarily unavailable. Please try again later.",
                },
            ) from None

        if result.status == GenerationStatus.NOT_CONFIGURED:
            status_code = 503
            error = "live_generation_not_configured"
        elif result.status in (GenerationStatus.PROVIDER_ERROR, GenerationStatus.INVALID_RESPONSE):
            status_code = 502
            error = result.status.value
        else:
            return _to_chat_response(result)

        payload = _to_chat_response(result, error=error)
        return JSONResponse(status_code=status_code, content=payload.model_dump())

    return application


app = create_app()
