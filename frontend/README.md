# PeopleDesk AI Static Frontend

The frontend remains the standalone HTML/CSS/JavaScript page in `docs/`. It submits questions to the backend API, shows a loading state, renders the returned answer and source citations, and handles abstention, configuration, and network errors. It has no canned answer path and never calls OpenAI directly.

## Configure the backend URL

The browser cannot read a process environment variable directly. Set the public `PEOPLEDESK_API_BASE_URL` variable, then generate `docs/api-config.js`:

```powershell
$env:PEOPLEDESK_API_BASE_URL = "http://127.0.0.1:8000"
python frontend/build_config.py
```

The backend URL is public browser configuration, not a secret. Never put `OPENAI_API_KEY` in this value or any frontend file. The checked-in default config is empty; the page then explains that the backend URL is not configured and makes no request.

## Run locally

From the repository root, start the API in one terminal:

```powershell
$env:FRONTEND_ORIGINS = "http://localhost:4173,http://127.0.0.1:4173"
python -m uvicorn backend.api.app:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, configure and serve the page using the commands above, then open `http://127.0.0.1:4173`. Add `OPENAI_API_KEY` only to the backend environment if live generation is desired. Without it, the API returns an explicit not-configured response rather than a mock answer.

## Checks

```bash
node --test frontend/tests/chat.test.cjs
python -m unittest frontend.tests.test_build_config -v
```

The existing static UI and responsive styles are retained; there is no React, TypeScript, npm, or bundler dependency.
