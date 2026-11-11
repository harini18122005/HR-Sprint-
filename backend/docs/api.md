# Frontend and Backend API

The HTTP layer in `backend/api/` connects the Day 7 static chat UI to the existing ingestion, BM25 retrieval, and grounded generation services. It reuses those services and does not return predefined policy answers.

## Endpoints

### `GET /api/health`

Returns service availability and whether answer generation has a configured provider:

```json
{
  "status": "ok",
  "generation_configured": false
}
```

### `POST /api/chat`

Request:

```json
{
  "question": "What are annual PTO accrual rates?"
}
```

Questions must contain 1–2000 non-whitespace characters. At startup, the API extracts and chunks the four checked-in sample policies using the existing Day 3/Day 4 pipeline. `PolicyRetriever` ranks those chunks. `AnswerGenerator` uses the configured provider and validates source chunk IDs and exact supporting quotes before citations are returned.

The response includes `answer`, `citations`, `abstained`, `status`, and an optional `error`. Each citation contains the actual filename (or known title/ID fallback), document ID, section when available, chunk ID, exact evidence quote, and page number only when available. Markdown policies have no page boundary metadata, so their page number stays `null`.

When retrieval finds no evidence, the API returns HTTP 200 with the existing abstention answer, an empty citation list, and `abstained: true`. When the OpenAI provider is not configured, it returns HTTP 503 with `status: "not_configured"`, a clear configuration message, and no invented answer. Provider failures and malformed output return HTTP 502 with safe messages. Invalid request bodies return HTTP 422; unexpected service errors return a generic HTTP 500 response without exception details.

## Run locally

Install dependencies from the repository root:

```bash
python -m pip install -r requirements.txt
```

Set the OpenAI key in the **backend process environment** to enable live answer generation. Never put this key in browser configuration. If unset, `/api/health` reports `generation_configured: false` and chat requests return a not-configured response; tests do not make live calls.

PowerShell, backend terminal:

```powershell
$env:FRONTEND_ORIGINS = "http://localhost:4173,http://127.0.0.1:4173"
$env:OPENAI_API_KEY = "your_real_key_here" # optional; omit to exercise the not-configured response
python -m uvicorn backend.api.app:app --reload --host 127.0.0.1 --port 8000
```

In a separate PowerShell terminal, configure and serve the static UI:

```powershell
$env:PEOPLEDESK_API_BASE_URL = "http://127.0.0.1:8000"
python frontend/build_config.py
python -m http.server 4173 --directory docs
```

Open `http://127.0.0.1:4173`. `docs/api-config.js` contains only the public backend URL. Do not use localhost for a remotely hosted UI; it points to each visitor's own computer. For the hosted Day 7 page, set `PEOPLEDESK_API_BASE_URL` to the deployed backend's public HTTPS origin and set `FRONTEND_ORIGINS` on the backend to the page's origin. This milestone does not deploy the backend.

## CORS

`FRONTEND_ORIGINS` is a comma-separated list of exact browser origins. Defaults allow the two local development origins on port 4173. Credentials are disabled; only `GET`, `POST`, and the `Content-Type` header are allowed. Set the hosted frontend origin explicitly when configuring a deployed backend.

## Tests

```bash
python -m unittest backend.tests.test_api -v
```

API tests use mocked providers and also exercise real sample-policy extraction, chunking, and retrieval. No paid OpenAI requests are made.
