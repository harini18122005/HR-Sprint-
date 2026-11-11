"""Tests for browser-visible API URL configuration generation."""

import tempfile
import unittest
from pathlib import Path

from frontend.build_config import normalize_api_base_url, write_api_config


class FrontendConfigTests(unittest.TestCase):
    def test_empty_url_is_allowed_for_unconfigured_preview(self) -> None:
        self.assertEqual(normalize_api_base_url("  "), "")

    def test_valid_url_is_trimmed_and_trailing_slashes_removed(self) -> None:
        self.assertEqual(
            normalize_api_base_url(" https://api.example.test/v1/// "),
            "https://api.example.test/v1",
        )

    def test_non_absolute_or_non_http_urls_are_rejected(self) -> None:
        for value in ("localhost:8000", "ftp://api.example.test", "//api.example.test"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_api_base_url(value)

    def test_urls_with_credentials_query_or_fragment_are_rejected(self) -> None:
        for value in (
            "https://user:secret@api.example.test",
            "https://api.example.test?token=secret",
            "https://api.example.test#fragment",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_api_base_url(value)

    def test_config_file_contains_json_escaped_public_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "api-config.js"
            write_api_config('https://api.example.test/path"quoted', destination)

            content = destination.read_text(encoding="utf-8")

        self.assertIn("window.PEOPLEDESK_CONFIG", content)
        self.assertIn('https://api.example.test/path\\"quoted', content)


if __name__ == "__main__":
    unittest.main()
