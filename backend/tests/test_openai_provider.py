"""Configuration and failure tests for the OpenAI Responses API adapter."""

import unittest
from types import SimpleNamespace

from backend.generation import GenerationConfig, OpenAIResponsesProvider
from backend.generation.providers import (
    ProviderError,
    ProviderNotConfiguredError,
    ProviderTimeoutError,
)


class OpenAIProviderTests(unittest.TestCase):
    def test_environment_factory_reads_key_and_model_without_exposing_key(self) -> None:
        provider = OpenAIResponsesProvider.from_environment({
            "OPENAI_API_KEY": "  test-secret-value  ",
            "OPENAI_MODEL": "  test-model  ",
        })

        self.assertTrue(provider.is_configured)
        self.assertNotIn("test-secret-value", repr(provider))
        self.assertIn("test-model", repr(provider))

    def test_missing_or_whitespace_key_is_not_configured(self) -> None:
        for key in (None, "", " \t "):
            with self.subTest(key=key):
                environment = {} if key is None else {"OPENAI_API_KEY": key}
                provider = OpenAIResponsesProvider.from_environment(environment)
                self.assertFalse(provider.is_configured)
                with self.assertRaises(ProviderNotConfiguredError):
                    provider.generate(
                        instructions="instructions",
                        input="input",
                        config=GenerationConfig(),
                    )

    def test_environment_model_is_used_and_blank_override_falls_back(self) -> None:
        class Responses:
            request = None

            def create(self, **kwargs):
                self.request = kwargs
                return SimpleNamespace(output_text="response")

        for model, expected in (("env-model", "env-model"), ("   ", "config-model")):
            with self.subTest(model=model):
                responses = Responses()
                provider = OpenAIResponsesProvider.from_environment(
                    {"OPENAI_API_KEY": "placeholder", "OPENAI_MODEL": model},
                    client=SimpleNamespace(responses=responses),
                )
                provider.generate(
                    instructions="instructions",
                    input="input",
                    config=GenerationConfig(model="config-model"),
                )
                self.assertEqual(responses.request["model"], expected)

    def test_provider_errors_are_sanitized(self) -> None:
        class Responses:
            def create(self, **kwargs):
                raise RuntimeError("private diagnostic and test-secret")

        provider = OpenAIResponsesProvider(
            "test-secret",
            client=SimpleNamespace(responses=Responses()),
        )

        with self.assertRaises(ProviderError) as raised:
            provider.generate(
                instructions="instructions",
                input="input",
                config=GenerationConfig(),
            )

        self.assertNotIn("test-secret", str(raised.exception))
        self.assertNotIn("private diagnostic", str(raised.exception))

    def test_empty_sdk_response_is_a_safe_provider_error(self) -> None:
        class Responses:
            def create(self, **kwargs):
                return SimpleNamespace(output_text=" \n ")

        provider = OpenAIResponsesProvider(
            "placeholder",
            client=SimpleNamespace(responses=Responses()),
        )

        with self.assertRaisesRegex(ProviderError, "did not contain output text"):
            provider.generate(
                instructions="instructions",
                input="input",
                config=GenerationConfig(),
            )

    def test_sdk_timeout_is_mapped_to_safe_timeout_error(self) -> None:
        import sys
        from unittest.mock import patch

        class APITimeoutError(Exception):
            pass

        class Responses:
            def create(self, **kwargs):
                raise APITimeoutError("private timeout detail")

        fake_sdk = SimpleNamespace(APIConnectionError=(), APITimeoutError=APITimeoutError)
        provider = OpenAIResponsesProvider(
            "placeholder",
            client=SimpleNamespace(responses=Responses()),
        )

        with patch.dict(sys.modules, {"openai": fake_sdk}):
            with self.assertRaises(ProviderTimeoutError) as raised:
                provider.generate(
                    instructions="instructions",
                    input="input",
                    config=GenerationConfig(),
                )

        self.assertNotIn("private timeout detail", str(raised.exception))
        self.assertEqual(provider.last_diagnostic.category, "timeout")

    def test_http_errors_are_classified_without_exposing_messages(self) -> None:
        class APIError(Exception):
            def __init__(self, status_code, code):
                super().__init__("private message containing test-secret")
                self.status_code = status_code
                self.code = code

        scenarios = (
            (401, "invalid_api_key", "authentication"),
            (403, "model_not_allowed", "permission_or_model_access"),
            (404, "model_not_found", "model_unavailable_or_endpoint_not_found"),
            (429, "insufficient_quota", "billing_or_quota"),
            (429, "rate_limit_exceeded", "rate_limit"),
            (400, "unsupported_parameter", "invalid_request"),
            (503, None, "provider_server_error"),
        )

        for status, code, expected_category in scenarios:
            with self.subTest(status=status, code=code):
                class Responses:
                    def create(self, **kwargs):
                        raise APIError(status, code)

                provider = OpenAIResponsesProvider(
                    "test-secret",
                    client=SimpleNamespace(responses=Responses()),
                )
                with self.assertLogs("backend.generation.providers", level="WARNING") as captured:
                    with self.assertRaises(ProviderError):
                        provider.generate(
                            instructions="instructions",
                            input="input",
                            config=GenerationConfig(),
                        )

                diagnostic = provider.last_diagnostic
                self.assertEqual(diagnostic.category, expected_category)
                self.assertEqual(diagnostic.http_status, status)
                self.assertNotIn("private message", repr(diagnostic.as_dict()))
                self.assertNotIn("test-secret", "\n".join(captured.output))

    def test_connection_failure_is_classified_as_network(self) -> None:
        class Responses:
            def create(self, **kwargs):
                raise ConnectionError("private endpoint details")

        provider = OpenAIResponsesProvider(
            "placeholder",
            client=SimpleNamespace(responses=Responses()),
        )
        with self.assertLogs("backend.generation.providers", level="WARNING"):
            with self.assertRaises(ProviderError):
                provider.generate(
                    instructions="instructions",
                    input="input",
                    config=GenerationConfig(),
                )
        self.assertEqual(provider.last_diagnostic.category, "network")
        self.assertNotIn("private endpoint", repr(provider.last_diagnostic.as_dict()))


if __name__ == "__main__":
    unittest.main()
