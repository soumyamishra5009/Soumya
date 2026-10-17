# Deploying SyncForge AI (live, no localhost, no PC)

This guide gets SyncForge running on a public URL using only free tiers. Once
it's set up, everything runs in the cloud — **your PC never has to be on**.

```
┌─────────────────┐      HTTPS       ┌──────────────────┐      ┌──────────────┐
│ Web (Next.js)   │ ───────────────► │ API (FastAPI)    │ ───► │ Postgres     │
│ Vercel          │                  │ Render (Docker)  │      │ Neon / Supa  │
└─────────────────┘                  └──────────────────┘      └──────────────┘
                                              │
                       ┌──────────────────────┼───────────────────────┐
                       ▼                      ▼                       ▼
                 Google Gemini          Groq Whisper            GitHub API
                 (LLM + embeddings)     (speech-to-text)        (optional push)
```

**Why not everything on Vercel?** Vercel serves the Next.js frontend perfectly,
but its serverless functions can't run the backend's real work — a writable
filesystem (Dev Studio), `git` (Ship It), and sandboxed subprocess test runs
(Verify). Render runs the API in a real container so every feature works. Both
platforms deploy straight from GitHub and stay online without your machine.

---

## 0. What you need (all free)

| Thing | Where | Used for |
|---|---|---|
| GitHub account | github.com | hosts the code, feeds both deploys |
| Google AI Studio key | aistudio.google.com/apikey | **Gemini** — the real LLM |
| Groq key | console.groq.com/keys | cloud speech-to-text |
| Neon account | neon.tech | free Postgres (data survives restarts) |
| Vercel account | vercel.com | the frontend (public URL) |
| Render account | render.com | the backend container |

> Everything works **without** Ollama. If no key is set at all, the app still
> runs on its offline extractive fallback — but you want real AI, so grab the
> Gemini key.

---

## 1. Push the code to GitHub

From the project root:

```bash
git remote add origin https://github.com/<you>/syncforge-ai.git
git branch -M main
git push -u origin main
```

## 2. Create the Postgres database (Neon)

1. neon.tech → **New Project** → copy the **connection string**.
2. Make sure it starts with `postgresql+psycopg2://` for SQLAlchemy, e.g.
   `postgresql+psycopg2://user:pass@ep-xxx.neon.tech/syncforge?sslmode=require`.

Keep this string for step 3.

## 3. Deploy the API to Render

1. Render Dashboard → **New +** → **Blueprint**.
2. Pick your repo. Render reads `render.yaml` and creates `syncforge-api`.
3. Fill the variables marked **sync: false**:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Neon string from step 2 |
   | `CORS_ORIGINS` | your Vercel URL (you'll paste it after step 4; any value works for now) |
   | `GEMINI_API_KEY` | your Google AI Studio key |
   | `GROQ_API_KEY` | your Groq key |
   | `GITHUB_TOKEN` | optional — enables real GitHub pushes/PRs |

   `SECRET_KEY` and `AUTH_SECRET` are generated automatically.
4. Deploy. When it's live, open `https://<your-api>.onrender.com/health` — you
   should see `{"status":"healthy", ...}`. Swagger docs are at `/docs`.

> **Free-tier note:** Render's free web service sleeps after ~15 minutes idle and
> cold-starts on the next request (about 30–60s). Open the Health URL once right
> before your demo so it's warm.

## 4. Deploy the web app to Vercel

1. Vercel → **Add New… → Project** → import the same repo.
2. **Root Directory** → `apps/web`  *(important: it's a monorepo)*.
3. Framework preset: **Next.js** (auto-detected).
4. Add an environment variable:

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://<your-api>.onrender.com` (no trailing slash) |

5. **Deploy**. Your public URL is `https://<your-app>.vercel.app`.

## 5. Close the loop (CORS)

Back in Render → `syncforge-api` → **Environment**, set:

```
CORS_ORIGINS=https://<your-app>.vercel.app
```

Save — Render redeploys automatically. Open your Vercel URL and register.

---

## Verification checklist

- [ ] `https://<api>.onrender.com/health` → `"status":"healthy"`
- [ ] Vercel URL loads the landing page
- [ ] Register → you land on the dashboard
- [ ] Create a meeting, upload audio → summary is **real Gemini output** (no
      `⚠️ Offline extractive summary` warning)
- [ ] Dev Studio → *Sample project* → open a file → ask the AI → proposal
- [ ] Verify → **Run tests** → `4 passed, 1 failed` → fix → green
- [ ] Project Memory → *Index workspace* → search returns semantic hits

---

## Optional: enable real GitHub pushes

Without `GITHUB_TOKEN`, Ship It uses the in-container **local git** provider —
fully functional, just not pushed to github.com. To enable real PRs:

1. github.com → Settings → Developer settings → **Personal access tokens**
   (fine-grained) → grant **Contents** and **Pull requests** (read/write) on the
   target repo.
2. Add it as `GITHUB_TOKEN` on Render.

---

## Local development still works

Nothing here removes the local setup — `npm run dev` at the repo root still
starts both servers with SQLite and the offline fallback. The cloud config is
just environment variables.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Frontend loads but API calls fail (`CORS`/`Failed to fetch`) | `CORS_ORIGINS` must exactly match the Vercel origin (scheme + host, no trailing slash). |
| Summaries show the ⚠️ offline notice | `GEMINI_API_KEY` not set, or the key is invalid/over quota. Check Render logs. |
| Audio transcription fails | Set `STT_ENGINE=groq_whisper` and a valid `GROQ_API_KEY`. |
| Render build fails on `av`/`psycopg2` | Make sure the service uses the Dockerfile (`requirements-cloud.txt`), not the full `requirements.txt`. |
| Vercel build: `Cannot find module '@syncforge/types'` / `monaco-editor` | It's a monorepo. Set **Root Directory** = `apps/web`, and in Project Settings → Build & Development enable *"Include source files outside of the Root Directory in the Build Step"*, and set **Install Command** to `cd ../.. && npm install`. |
| First request is slow | Render free tier cold start — open `/health` to warm it. |
| Dev Studio files vanish after a while | Free tier has no persistent disk; re-run *Sample project*. Data in Postgres (meetings, tasks, memory) is safe. |
