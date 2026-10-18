# Deploying SyncForge AI (live, no localhost, no PC)

This guide gets SyncForge running on a public URL using only free tiers, with a
**single API key** (Google Gemini). Once it's set up, everything runs in the
cloud — **your PC never has to be on**.

```
                        ┌──────────────────────────────────────┐
                        │  Vercel (one project, one URL)       │
  browser ─────────────►│  ┌─────────────┐   ┌──────────────┐  │      ┌──────────────┐
  /            │  Next.js web   │──►│ FastAPI API   │  │ ───► │ Neon         │
  /api/v1/* ───────────►│  (apps/web)   │   │ (apps/api)   │  │      │ (Postgres)   │
                        └─────────────┘   └──────┬───────┘  │      └──────────────┘
                                                 │              │
                                  Google Gemini ◄─┘              │
                                  (LLM + speech-to-text         │
                                   + embeddings — one key)      │
```

The repo root is a **Vercel Services** project (`vercel.json`): two services —
`backend` (FastAPI, `apps/api`) and `frontend` (Next.js, `apps/web`) — share
one domain. A public routing rule sends `/api/v1/*` (plus `/health`, `/docs`)
to the backend and everything else to the frontend, so the browser calls the
API **same-origin** — no CORS setup, no `NEXT_PUBLIC_API_URL`.

> **Why this used to be harder:** serverless hosts have no Docker, no local
> Whisper, and no persistent disk. SyncForge solves each one in-process:
> Dev Studio stores its file tree as database rows, Verify runs the bundled
> test runner via subprocess in `/tmp`, STT is Gemini audio transcription, and
> uploads land in `/tmp`. Zero extra services, zero extra keys.

---

## 0. What you need (all free)

| Thing | Where | Used for |
|---|---|---|
| GitHub account | github.com | hosts the code, feeds the deploy |
| Vercel account | vercel.com | hosts web + API + database binding |
| Google AI Studio key | aistudio.google.com/apikey | **Gemini** — LLM, speech-to-text, embeddings |
| Neon (via Vercel Marketplace) | vercel.com/marketplace | free Postgres (data survives restarts) |

That's the complete list. No Groq, no OpenRouter, no Ollama, no Docker.

> The app still runs without the Gemini key on its offline extractive
> fallback — but you want real AI, so grab the key.

---

## 1. Push the code to GitHub

From the project root:

```bash
git remote add origin https://github.com/<you>/syncforge-ai.git
git branch -M main
git push -u main
```

## 2. Create the Vercel project (Services mode)

1. Vercel → **Add New… → Project** → import your repo.
2. **Root Directory** stays at the repo root (this is a monorepo; the Services
   config in `vercel.json` points at `apps/api` and `apps/web`).
3. Select the **Services** framework preset:
   - Dashboard: Project → Settings → General → **Framework Preset** → *Services*; or
   - CLI: `vercel project update --framework services`
4. Leave the build settings alone — `vercel.json` already declares both
   services, the `/api/v1/*` routing rule, and Python function limits.

## 3. Connect the database (Neon, free)

1. Vercel → your project → **Storage** → **Marketplace** → **Neon** → create a
   free database and connect it to the **backend** service (all environments).
2. Vercel injects `DATABASE_URL` automatically. The API normalises bare
   `postgresql://…` URLs to `postgresql+psycopg2://…` on startup, so the
   copy-pasted string just works. No migrations to run — tables are created on
   first boot (`init_db`), including the Dev Studio file store.

## 4. Set environment variables

Project → Settings → Environment Variables:

| Key | Required | Value |
|---|---|---|
| `GEMINI_API_KEY` | **yes** | your Google AI Studio key |
| `GITHUB_TOKEN` | no | enables real GitHub pushes/PRs in Ship It |
| `GEMINI_MODEL` | no | override the default Gemini chat model |
| `LLM_PROVIDER_ORDER` | no | default `gemini,openrouter,ollama` |
| `PISTON_API_KEY` | no | only if you swap Verify to the Piston executor |

Cloud behaviour is applied automatically when Vercel sets `VERCEL=1` — no
configuration needed for any of this:

| Subsystem | Cloud default | How it works on Vercel |
|---|---|---|
| Speech-to-text | `STT_ENGINE=gemini` | Gemini audio transcription — no Whisper model, no Groq key |
| Dev Studio | `DEVSTUDIO_BACKEND=db` | the workspace tree lives in Postgres (`WorkspaceFile` rows) |
| Verify | `CODE_EXECUTOR=local` | the bundled runner executes via subprocess in a temp dir (`/tmp` is writable on Functions) |
| Uploads | `/tmp/syncforge-uploads` | audio is transcribed in-flight; nothing needs to persist |
| Embeddings | Gemini `text-embedding-004` | project memory RAG with no local model |

## 5. Deploy

`vercel --prod` (or press **Deploy** in the dashboard). Your URL is
`https://<your-app>.vercel.app` — it serves the web app, the API
(`/api/v1/...`), Swagger at `/docs`, and `/health`.

---

## Verification checklist

- [ ] `https://<your-app>.vercel.app/health` → `"status":"healthy"`
- [ ] The URL loads the landing page; register → you land on the dashboard
- [ ] Create a meeting, upload audio → summary is **real Gemini output** (no
      `⚠️ Offline extractive summary` warning) and the transcript is real STT
- [ ] Dev Studio → *Sample project* → open a file → ask the AI → proposal →
      approve → the file updates (stored in Postgres)
- [ ] Verify → **Run tests** → `4 passed, 1 failed` → approve the fix → green
- [ ] Project Memory → *Index workspace* → search returns semantic hits

---

## Optional: enable real GitHub pushes

Without `GITHUB_TOKEN`, Ship It runs in cloud mode with local git disabled
(the UI explains this; everything up to the patch export works). To enable
real PRs:

1. github.com → Settings → Developer settings → **Personal access tokens**
   (fine-grained) → grant **Contents** and **Pull requests** (read/write) on
   the target repo.
2. Add it as `GITHUB_TOKEN` on Vercel.

---

## Local development still works

Nothing here removes the local setup — `npm run dev` at the repo root still
starts both servers with SQLite and the offline fallback.

> **Note:** `requirements.txt` is now the lean Vercel runtime set (no local
> Whisper/Celery). For the full local experience install the extras once:
>
> ```bash
> cd apps/api && pip install -r requirements-dev.txt
> ```

The alternative container path (Render/Fly/Railway + `Dockerfile` +
`render.yaml`) is still in the repo if you ever want a persistent-disk host.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Vercel only builds the frontend | Framework Preset must be **Services** (`vercel project update --framework services`) and Root Directory must be the repo root. |
| API routes 404 | `vercel.json` must be at the repo root with the `/api/v1/(.*)` → backend rewrite before the frontend catch-all. |
| Summaries show the ⚠️ offline notice | `GEMINI_API_KEY` not set on the project, or invalid/over quota — check the backend function logs. |
| Audio transcription fails | Confirm `GEMINI_API_KEY`; `STT_ENGINE` is already `gemini` on Vercel. Very long files may exceed the function's max duration — trim the audio. |
| Verify says the sandbox is empty | Open Dev Studio → *Sample project* first (the tree lives in Postgres). |
| Verify fails on Node projects | The Python runtime has no `node` binary; Python tests are the supported cloud path (local/Docker hosts run JS tests too). |
| `DATABASE_URL` errors at boot | The Neon integration must be attached to the **backend** service; the API accepts bare `postgresql://` strings and normalises them. |
| Dev Studio edits don't persist | Ensure `DEVSTUDIO_BACKEND=db` is not overridden — on Vercel it's the default. |
| Local `pip install` looks thin | By design: `requirements.txt` is the lean Vercel set — use `requirements-dev.txt` for local extras. |
