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

        fake_sdk = SimpleNamespace(APITimeoutError=APITimeoutError)
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


if __name__ == "__main__":
    unittest.main()
