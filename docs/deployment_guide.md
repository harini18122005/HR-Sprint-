# Viva Deployment Guide

This repository has a static HTML/CSS/JavaScript frontend and a FastAPI backend. The quickest low-cost setup is GitHub Pages for the static page and a Render Web Service for the API. The API loads the four checked-in sample policies at startup and uses the existing BM25 retrieval and answer-generation pipeline.

## Deployment files

- `render.yaml` defines the FastAPI service, Python runtime, start command, health check, model, frontend CORS origin, and a secret prompt for `OPENAI_API_KEY`.
- `.python-version` requests Python 3.11.
- `.github/workflows/deploy-pages.yml` builds the browser-visible API URL from the optional repository variable `PEOPLEDESK_API_BASE_URL` (default: `https://hr-sprint-2.onrender.com`) and deploys `docs/` to GitHub Pages. The URL is public configuration, not a secret.
- The browser API URL is public configuration. The OpenAI key is only a backend secret and must never be put in a GitHub variable, browser file, or frontend setting.

## Current hosting state

The GitHub Pages URL is `https://harini18122005.github.io/HR-Sprint-/`. The integrated frontend is ready only after **Deploy PeopleDesk AI frontend** completes successfully. A published page or successful health check alone does not prove that chat and citations work.

The GitHub Pages deployment workflow publishes after its changes are merged to `main`. The API permits the fixed Pages origin `https://harini18122005.github.io` by default. If the Pages URL or Render service URL changes, update `FRONTEND_ORIGINS` in Render and `PEOPLEDESK_API_BASE_URL` in the repository variables.

## Manual deployment steps

The Render backend already exists at `https://hr-sprint-2.onrender.com`; do not create a second service for this repository.

1. In Render, open the existing **HR-Sprint-2** service and select **Environment**.
2. Confirm `OPENAI_API_KEY` is the exact variable name. Keep its value hidden. Confirm `OPENAI_MODEL` is `gpt-6-astra` and `FRONTEND_ORIGINS` includes `https://harini18122005.github.io`.
3. If you changed an environment value, save it and wait for the service to redeploy.
4. To diagnose a chat failure, open the service-level **Logs** page (not only a deployment log), submit a question through `/docs`, then look for the sanitized `OpenAI request failed` line. Share only its category, exception, status, and code; never share the key or request body.
5. In GitHub **Settings** → **Pages**, set **Build and deployment** → **Source** to **GitHub Actions** if it is not already selected.
6. After the deployment fix reaches `main`, open the repository **Actions** tab and wait for **Deploy PeopleDesk AI frontend** to succeed before presenting the page.
7. The workflow uses `https://hr-sprint-2.onrender.com` by default. If the Render service URL changes, set the Actions repository variable `PEOPLEDESK_API_BASE_URL` to the new public HTTPS origin. Never put the OpenAI key in GitHub.

If Render asks for a payment method or offers a paid plan, stop and review the price in your account before accepting. The configured Free web service has no charge for compute within Render's free allowance, but it sleeps after 15 minutes idle and can take about one minute to wake. For a viva, open the health URL shortly before presenting and wait for its response. A paid plan avoids the free service's idle sleep but requires your separate billing approval.

## Verify before the viva

Use the deployed Render health URL:

```text
https://hr-sprint-2.onrender.com/api/health
```

Expect HTTP 200 with `status: "ok"` and `generation_configured: true`. From PowerShell, test a policy question:

```powershell
$api = "https://hr-sprint-2.onrender.com"
Invoke-RestMethod -Method Post -Uri "$api/api/chat" -ContentType "application/json" -Body '{"question":"How many PTO days can an employee carry over?"}'
```

Confirm the response has `status: "generated"`, an answer, and citations containing the policy document, section, chunk ID, and evidence quote. Also test an unsupported question and confirm it abstains. The opt-in check sends five real API requests and may incur model usage charges:

```powershell
python -m backend.scripts.live_generation_check
```

`generation_configured: true` only confirms that an API key value is present; a successful `/api/chat` response is required to verify live generation.

Open `https://harini18122005.github.io/HR-Sprint-/`, ask a sample policy question, and confirm the answer and source citation render. The GitHub Actions run must be successful for the updated frontend to be available.

## Hosting limitations

- The deployment exposes fictional sample HR policies only; it is not connected to company policy data, employee identity, or authentication.
- Render's Free service can cold-start and is suitable for a demo, not reliable production availability.
- A public static site sends questions to the public API. Do not enter personal or confidential employee information.
- No public backend URL exists until the Render Blueprint is created and its deploy finishes. Do not present a guessed URL as live.
