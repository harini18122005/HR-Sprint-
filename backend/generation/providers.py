"""Provider interface and optional OpenAI Responses API implementation."""

from dataclasses import dataclass
import logging
import os
import re
from typing import Mapping, Optional, Protocol


class ProviderError(RuntimeError):
    """Base exception for failures while requesting generated text."""


class ProviderNotConfiguredError(ProviderError):
    """Raised when credentials or the provider SDK are unavailable."""


class ProviderTimeoutError(ProviderError):
    """Raised when the configured provider request times out."""


@dataclass(frozen=True)
class ProviderDiagnostic:
    """Safe provider failure metadata; never stores exception messages or credentials."""

    category: str
    exception_type: str
    http_status: Optional[int] = None
    api_error_code: Optional[str] = None

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "exception_type": self.exception_type,
            "http_status": self.http_status,
            "api_error_code": self.api_error_code,
        }


logger = logging.getLogger(__name__)
_SAFE_ERROR_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_QUOTA_CODES = {"insufficient_quota", "billing_hard_limit_reached", "billing_not_active"}
_RATE_LIMIT_CODES = {"rate_limit_exceeded", "requests_limit_exceeded", "tokens_limit_exceeded"}


@dataclass(frozen=True)
class GenerationConfig:
    """Settings shared by generation providers."""

    model: str = "gpt-6-astra"
    max_output_tokens: int = 700
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model must be a non-empty string.")
        if isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int):
            raise ValueError("max_output_tokens must be a positive integer.")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive integer.")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")


class TextGenerationProvider(Protocol):
    """Provider contract consumed by the answer-generation service."""

    def generate(
        self,
        *,
        instructions: str,
        input: str,
        config: GenerationConfig,
    ) -> str:
        """Return generated text for the supplied instructions and input."""


class OpenAIResponsesProvider:
    """Lazy OpenAI Python SDK provider using the Responses API.

    The SDK is imported only for a configured live request, so mock-based tests
    and users without credentials do not need to make an API call.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        client: object = None,
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key else None
        self._client = client
        self._model = model.strip() if model and model.strip() else None
        self._last_diagnostic: Optional[ProviderDiagnostic] = None

    def __repr__(self) -> str:
        """Keep credentials out of diagnostic output and accidental logs."""
        return (
            f"{type(self).__name__}(api_key='[redacted]', "
            f"configured={self.is_configured!r}, model={self._model!r})"
        )

    @classmethod
    def from_environment(
        cls,
        environ: Optional[Mapping[str, str]] = None,
        *,
        client: object = None,
    ) -> "OpenAIResponsesProvider":
        """Build a provider from OPENAI_API_KEY without displaying the key."""
        source = os.environ if environ is None else environ
        return cls(
            source.get("OPENAI_API_KEY"),
            client=client,
            model=source.get("OPENAI_MODEL"),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def last_diagnostic(self) -> Optional[ProviderDiagnostic]:
        """Return structured, non-secret metadata for the most recent failed call."""
        return self._last_diagnostic

    def generate(
        self,
        *,
        instructions: str,
        input: str,
        config: GenerationConfig,
    ) -> str:
        if not self.is_configured:
            raise ProviderNotConfiguredError(
                "OPENAI_API_KEY is not configured; no live answer was generated."
            )

        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise ProviderNotConfiguredError(
                    "The OpenAI SDK is not installed; install requirements.txt to enable live generation."
                ) from error
        else:
            OpenAI = None

        selected_model = self._model or config.model
        self._last_diagnostic = None
        try:
            if self._client is None:
                self._client = OpenAI(
                    api_key=self._api_key,
                    timeout=config.timeout_seconds,
                    max_retries=0,
                )
            response = self._client.responses.create(
                model=selected_model,
                instructions=instructions,
                input=input,
                max_output_tokens=config.max_output_tokens,
            )
        except Exception as error:
            diagnostic = self._diagnose_error(error)
            self._last_diagnostic = diagnostic
            logger.warning(
                "OpenAI request failed (category=%s exception=%s status=%s code=%s)",
                diagnostic.category,
                diagnostic.exception_type,
                diagnostic.http_status,
                diagnostic.api_error_code,
            )
            if diagnostic.category == "timeout":
                raise ProviderTimeoutError("The OpenAI request timed out.") from error
            raise ProviderError("The OpenAI Responses API request failed.") from error

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise ProviderError("The OpenAI response did not contain output text.")
        return output_text.strip()

    @staticmethod
    def _diagnose_error(error: Exception) -> ProviderDiagnostic:
        """Classify provider failures using only safe exception metadata."""
        exception_type = type(error).__name__
        raw_status = getattr(error, "status_code", None)
        status = raw_status if isinstance(raw_status, int) and 100 <= raw_status <= 599 else None
        raw_code = getattr(error, "code", None)
        code = raw_code if isinstance(raw_code, str) and _SAFE_ERROR_CODE.fullmatch(raw_code) else None
        normalized_code = code.casefold() if code else None

        try:
            from openai import APIConnectionError, APITimeoutError
        except ImportError:
            APIConnectionError = ()  # type: ignore[assignment,misc]
            APITimeoutError = ()  # type: ignore[assignment,misc]

        if (APITimeoutError and isinstance(error, APITimeoutError)) or isinstance(error, TimeoutError):
            category = "timeout"
        elif (APIConnectionError and isinstance(error, APIConnectionError)) or isinstance(error, ConnectionError):
            category = "network"
        elif status == 401 or normalized_code == "invalid_api_key":
            category = "authentication"
        elif status == 403:
            category = "permission_or_model_access"
        elif status == 404 or normalized_code == "model_not_found":
            category = "model_unavailable_or_endpoint_not_found"
        elif status == 429 and normalized_code in _QUOTA_CODES:
            category = "billing_or_quota"
        elif status == 429 and normalized_code in _RATE_LIMIT_CODES:
            category = "rate_limit"
        elif status == 429:
            category = "rate_limit_or_quota"
        elif status == 400:
            category = "invalid_request"
        elif status is not None and status >= 500:
            category = "provider_server_error"
        elif status is not None:
            category = "provider_http_error"
        else:
            category = "provider_request_error"

        return ProviderDiagnostic(
            category=category,
            exception_type=exception_type,
            http_status=status,
            api_error_code=code,
        )
