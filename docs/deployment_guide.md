# Viva Deployment Guide

This repository has a static HTML/CSS/JavaScript frontend and a FastAPI backend. The quickest low-cost setup is GitHub Pages for the static page and a Render Web Service for the API. The API loads the four checked-in sample policies at startup and uses the existing BM25 retrieval and answer-generation pipeline.

## Deployment files

- `render.yaml` defines the FastAPI service, Python runtime, start command, health check, model, frontend CORS origin, and a secret prompt for `OPENAI_API_KEY`.
- `.python-version` requests Python 3.11.
- `.github/workflows/deploy-pages.yml` builds the browser-visible API URL from the GitHub repository variable `PEOPLEDESK_API_BASE_URL` and deploys `docs/` to GitHub Pages. It fails rather than publishing a page with an empty API URL.
- The browser API URL is public configuration. The OpenAI key is only a backend secret and must never be put in a GitHub variable, browser file, or frontend setting.

## Current hosting state

The existing GitHub Pages URL is `https://harini18122005.github.io/HR-Sprint-/`. At the time this guide was prepared, that page was configured to publish `/docs` from branch `sprint/day-7-ui-mockup`; it was not publishing the current frontend/backend integration from `main`. The public page responded with HTTP 200, but that does not mean the API is deployed or connected.

The GitHub Pages deployment workflow publishes after this deployment PR is merged to `main`. The workflow uses the fixed Pages origin `https://harini18122005.github.io` for CORS. If the Pages URL or custom domain changes, update `FRONTEND_ORIGINS` in `render.yaml` and the Actions repository variable before deploying again.

## Manual deployment steps

These steps require you to sign in and authorize Render to access the GitHub repository. Enter the OpenAI key only in Render's environment variable prompt; do not send it in chat or add it to a repository file.

1. Review and merge the deployment PR to `main` yourself. Merging is required for the Pages workflow, which only deploys code on `main`.
2. Open [Render Dashboard](https://dashboard.render.com/) and sign in.
3. Select **New +** → **Blueprint**.
4. Connect the GitHub account if prompted, select `harini18122005/HR-Sprint-`, and choose branch `main` after the deployment PR is merged. Render will read the root `render.yaml`.
5. Review the service settings. The Blueprint uses Render's **Free** plan to avoid requiring billing. Choose the Singapore region as configured.
6. When Render prompts for `OPENAI_API_KEY`, enter the key directly in the Render dashboard field. Never paste it into this repository or Codex chat. Confirm `OPENAI_MODEL` is `gpt-6-astra` and `FRONTEND_ORIGINS` is `https://harini18122005.github.io`.
7. Click **Apply** / **Create Blueprint** and wait for the `peopledesk-ai-api` service to finish deploying. Copy its public `https://…onrender.com` origin from the service page; do not append `/api`.
8. In GitHub, open the repository **Settings** → **Secrets and variables** → **Actions** → **Variables** → **New repository variable**. Name it `PEOPLEDESK_API_BASE_URL` and set its value to the Render service's public HTTPS origin, such as `https://your-service.onrender.com`. This is a public URL, not a secret.
9. In GitHub **Settings** → **Pages**, set **Build and deployment** → **Source** to **GitHub Actions**, then save.
10. Open the repository **Actions** tab and watch **Deploy PeopleDesk AI frontend**. The run should complete successfully before using the page.

If Render asks for a payment method or offers a paid plan, stop and review the price in your account before accepting. The configured Free web service has no charge for compute within Render's free allowance, but it sleeps after 15 minutes idle and can take about one minute to wake. For a viva, open the health URL shortly before presenting and wait for its response. A paid plan avoids the free service's idle sleep but requires your separate billing approval.

## Verify before the viva

Use the exact Render origin displayed in the dashboard:

```text
https://<render-service>.onrender.com/api/health
```

Expect HTTP 200 with `status: "ok"` and `generation_configured: true`. From PowerShell, test a policy question after substituting the public origin:

```powershell
$api = "https://<render-service>.onrender.com"
Invoke-RestMethod -Method Post -Uri "$api/api/chat" -ContentType "application/json" -Body '{"question":"How many PTO days can an employee carry over?"}'
```

Confirm the response has `status: "generated"`, an answer, and citations containing the policy document, section, chunk ID, and evidence quote. Also test an unsupported question and confirm it abstains. The opt-in check sends five real API requests and may incur model usage charges:

```powershell
python -m backend.scripts.live_generation_check
```

Open `https://harini18122005.github.io/HR-Sprint-/`, ask a sample policy question, and confirm the answer and source citation render. The GitHub Actions run must be successful for the updated frontend to be available.

## Hosting limitations

- The deployment exposes fictional sample HR policies only; it is not connected to company policy data, employee identity, or authentication.
- Render's Free service can cold-start and is suitable for a demo, not reliable production availability.
- A public static site sends questions to the public API. Do not enter personal or confidential employee information.
- No public backend URL exists until the Render Blueprint is created and its deploy finishes. Do not present a guessed URL as live.
