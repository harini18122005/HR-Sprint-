"""Generate the static frontend's public API URL config from an environment variable."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "api-config.js"


def normalize_api_base_url(value: str) -> str:
    """Validate and normalize a browser-visible HTTP(S) backend URL."""
    normalized = value.strip().rstrip("/")
    if not normalized:
        return ""

    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("PEOPLEDESK_API_BASE_URL must be an absolute http:// or https:// URL.")
    if parsed.username or parsed.password:
        raise ValueError("PEOPLEDESK_API_BASE_URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("PEOPLEDESK_API_BASE_URL must not contain a query string or fragment.")
    return normalized


def write_api_config(api_base_url: str, output_path: Path = DEFAULT_OUTPUT) -> Path:
    """Write a JavaScript config file; the URL is public and must contain no secret."""
    normalized = normalize_api_base_url(api_base_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "window.PEOPLEDESK_CONFIG = Object.freeze({ apiBaseUrl: "
        f"{json.dumps(normalized)} }});\n",
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    api_base_url = os.environ.get("PEOPLEDESK_API_BASE_URL", "")
    output_path = write_api_config(api_base_url)
    if api_base_url.strip():
        print(f"Wrote browser API config to {output_path.relative_to(PROJECT_ROOT)}")
    else:
        print("PEOPLEDESK_API_BASE_URL is empty; the page will show a backend-not-configured message.")


if __name__ == "__main__":
    main()
