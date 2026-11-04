"""Provider interface and optional OpenAI Responses API implementation."""

from dataclasses import dataclass
import os
from typing import Mapping, Optional, Protocol


class ProviderError(RuntimeError):
    """Base exception for failures while requesting generated text."""


class ProviderNotConfiguredError(ProviderError):
    """Raised when credentials or the provider SDK are unavailable."""


class ProviderTimeoutError(ProviderError):
    """Raised when the configured provider request times out."""


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
        self._model = model

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
            self._client = OpenAI(
                api_key=self._api_key,
                timeout=config.timeout_seconds,
                max_retries=0,
            )

        try:
            response = self._client.responses.create(
                model=self._model or config.model,
                instructions=instructions,
                input=input,
                max_output_tokens=config.max_output_tokens,
            )
        except Exception as error:
            try:
                from openai import APITimeoutError
            except ImportError:
                APITimeoutError = ()  # type: ignore[assignment,misc]

            if APITimeoutError and isinstance(error, APITimeoutError):
                raise ProviderTimeoutError("The OpenAI request timed out.") from error
            raise ProviderError("The OpenAI Responses API request failed.") from error

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise ProviderError("The OpenAI response did not contain output text.")
        return output_text.strip()
