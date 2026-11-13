# Local Setup Guide

These steps run the existing static UI and Python API on a developer computer. They do not deploy either component.

## Requirements

- Python 3.11 (the project code and test environment use Python 3.11).
- Git.
- A modern web browser.
- Node.js 18+ if you want to run the frontend interaction tests (Node.js 20+ is recommended). The frontend itself has no npm dependencies, `package.json`, or build step.
- Internet access to install Python packages. A live OpenAI API key is optional and is not needed for the test suite.

## Clone and create a virtual environment

In PowerShell:

```powershell
git clone https://github.com/harini18122005/HR-Sprint-.git
Set-Location HR-Sprint-
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation in your environment, use the virtual environment interpreter directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS/Linux, create and activate the environment with `python3.11 -m venv .venv` and `source .venv/bin/activate`, then install `python -m pip install -r requirements.txt`.

## Configure environment variables

The application reads environment variables from the process. It does **not** load `.env` files automatically. `.env.example` is a placeholder reference; it contains no usable key.

In the backend PowerShell terminal, set the allowed frontend origins:

```powershell
$env:FRONTEND_ORIGINS = "http://localhost:4173,http://127.0.0.1:4173"
```

Live generation is optional. If you have an authorized OpenAI key, set it only in the backend terminal or deployment secret store:

```powershell
$env:OPENAI_API_KEY = "<your key>"
# Optional model override:
$env:OPENAI_MODEL = "<model available to your account>"
```

Do not paste a real key into source files, browser configuration, screenshots, or commits. Without a key, `/api/health` reports `generation_configured: false`; a question with evidence returns a clear HTTP 503 not-configured response.

## Start the backend

In the first terminal, from the repository root with the virtual environment active:

```powershell
python -m uvicorn backend.api.app:app --reload --host 127.0.0.1 --port 8000
```

Check `http://127.0.0.1:8000/api/health`. The checked-in sample policies are extracted and chunked when the API app initializes.

## Configure and start the frontend

Open a second terminal, activate the same virtual environment, then:

```powershell
$env:PEOPLEDESK_API_BASE_URL = "http://127.0.0.1:8000"
python frontend/build_config.py
python -m http.server 4173 --directory docs
```

Open `http://127.0.0.1:4173`. `PEOPLEDESK_API_BASE_URL` is a public backend origin, not a place for secrets. Running the config generator with an empty variable writes an empty URL; the browser then displays a backend-not-configured message.

For non-local hosting, `localhost` will point to each visitor's own computer. Use the deployed backend's public HTTPS origin in `PEOPLEDESK_API_BASE_URL` and set `FRONTEND_ORIGINS` to the exact UI origin. This repository does not deploy or configure hosting for the backend.

## Run the tests

From the repository root:

```powershell
python -m unittest discover -s backend/tests -v
node --test frontend/tests/chat.test.cjs
python -m unittest frontend.tests.test_build_config -v
```

These tests use mocked generation providers and make no paid OpenAI calls. Passing tests do not verify live model behavior or credentials.

## Common setup issues

| Symptom | Resolution |
|---|---|
| `ModuleNotFoundError` for FastAPI, OpenAI, or HTTPX | Activate `.venv` and run `python -m pip install -r requirements.txt`. |
| `py -3.11` cannot find Python | Install Python 3.11 and enable the Python launcher, or use an installed Python 3.11 interpreter explicitly. |
| Port 8000 or 4173 is already in use | Stop the other process or choose another port; update `FRONTEND_ORIGINS` and `PEOPLEDESK_API_BASE_URL` to match. |
| Browser says backend URL is not configured | Set `PEOPLEDESK_API_BASE_URL`, run `python frontend/build_config.py`, and reload the page. |
| Browser reports a network/CORS problem | Ensure Uvicorn is running and `FRONTEND_ORIGINS` exactly matches the page origin, including scheme and port; restart the API after changing it. |
| API returns HTTP 503 and `not_configured` | The backend has no OpenAI key. This is expected without live configuration; the API will not invent a mock answer. |
| Chat returns an insufficient-evidence message | The question did not match retrieved sample policy chunks. Try a question about PTO, core hours, HSA, or reporting conduct violations. |

For endpoint and response details see [the API documentation](../backend/docs/api.md). For the demo sequence see [the demo guide](demo_guide.md).
