# SyncForge AI

> An AI-powered workspace that automates the entire flow: **Meetings → Decisions → Tasks → Code → Verification**

## 🚀 Vision

SyncForge AI bridges the gap between discussions and execution. Instead of meeting notes getting lost, it extracts actionable decisions, converts them into trackable tasks, and helps implement them directly through an AI coding agent — all inside one unified workspace.

## ✨ Key Features

| Feature | Description |
|---|---|
| **AI Meeting Intelligence** | Upload audio/meetings and get transcripts with speaker timestamps, summaries, key decisions, action items, risks and unanswered questions. Supports English + Hinglish. |
| **Editable AI Output** | Human-in-the-loop: edit the summary, key points, risks, questions and every decision inline — or add/delete decisions the AI missed. Nothing is locked. |
| **Smart Action Tracker** | Auto-generated tasks linked to their source meeting. Kanban board with drag & drop, assignees (avatars), priorities, due dates, overdue alerts and filters (search, assignee, priority, due date, "My tasks"). |
| **Team & Meetings History** | Add teammates by email (owner/admin), assign work to them, and keep a searchable meeting history with an archive. |
| **AI Dev Studio** | Browser-based, workspace-scoped coding workspace: file explorer, Monaco Editor (bundled locally, no CDN), context-aware AI Chat (aware of the open file + file tree + a linked Meeting/Task) and an offline static analyzer. |
| **Human-approved change proposals** | The AI *proposes* full-file edits as a side-by-side diff with a rationale. Nothing is written to disk until a teammate approves it — and stale proposals (file changed since) are refused. |
| **Meeting-to-Code Agent** | Converts meeting decisions into technical requirements, breaks them into subtasks, identifies relevant files and proposes code changes as diffs with human approval. |
| **GitHub Integration** | Connect repositories and have AI propose changes via Pull Requests (write access never auto-granted, human approval is mandatory). |
| **Sandbox Code Execution** | Isolated code execution via Judge0/E2B to safely run AI-generated code and tests. |
| **Project Memory (RAG)** | Semantic search across meetings, documents and codebase using `pgvector`. Ask questions like *"Humne authentication ke liye kya decide kiya tha?"* with source references. |
| **Commitment Tracker** | Links commitments made in meetings to tasks and tracks completion with AI-generated weekly progress reports. |

## 🛠 Tech Stack

| Layer | Tech | Notes |
|---|---|---|
| **Frontend** | [Next.js 15](https://nextjs.org/) (App Router), TypeScript, [Tailwind CSS](https://tailwindcss.com/), [shadcn/ui](https://ui.shadcn.com/), [Monaco Editor](https://microsoft.github.io/monaco-editor/) | Modern, type-safe UI |
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+) | High-performance API |
| **Database** | **SQLite** (zero-setup dev) → [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) (production) | Swap with `DATABASE_URL` |
| **Auth** | JWT (bcrypt) issued by the FastAPI | Phase 1 — OAuth via Auth.js lands later |
| **STT** | [Gemini audio transcription](https://aistudio.google.com/apikey) (cloud, same key) or [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (local, free) | Gemini = zero local setup; local = fully offline |
| **LLMs** | [Google Gemini](https://aistudio.google.com/apikey) (cloud, free) → [OpenRouter](https://openrouter.ai/) (cloud fallback) → [Ollama](https://ollama.com/) (local) + **offline extractive fallback** | Cloud-first, free, nothing to install; still works with *no* AI service |
| **Queue/Worker** | [Celery](https://docs.celeryq.dev/) + [Redis](https://redis.io/) | Background jobs (transcription, agent runs) |
| **Code Execution** | Bundled sandboxed runner (default, zero deps) → optional [Judge0](https://github.com/judge0/judge0) / [E2B](https://e2b.dev/) / [Piston](https://github.com/engineer-man/piston) | Works locally, in Docker and on Vercel (`/tmp` sandbox) |
| **Storage** | [Supabase Storage](https://supabase.com/storage) or Local | Audio/files storage |
| **Git** | [GitHub REST/GraphQL API](https://docs.github.com/en/rest) | Repo access, PR proposals |

## 📁 Project Structure

```text
Saumya/
├── README.md
├── .env.example
├── docker-compose.yml        # Postgres, Redis, Judge0 (optional)
├── package.json              # Monorepo root scripts
├── turbo.json                # Turborepo config
├── apps/
│   ├── web/                  # Next.js Frontend
│   └── api/                  # FastAPI Backend
├── packages/
│   ├── database/             # DB schemas/migrations (Prisma/SQL)
│   ├── types/                # Shared TypeScript + Pydantic types
│   └── config/               # Shared config/env validation
├── docs/                     # Architecture, prompts, ADRs
└── scripts/                  # Setup, seed, utility scripts
```

## 🗺 Roadmap

| Phase | Timeline | Goal |
|---|---|---|
| **Phase 1** | Day 1–2 | Scaffold + DB + Auth + Audio Upload + STT + AI Summary + Decisions/Action Items |
| **Phase 2** | Day 3–4 | Kanban Board + Meeting→Task Linking + Editable AI Outputs + Meeting History + Team members/assignees |
| **Phase 3** | Day 5–6 | AI Dev Studio (Monaco + File Explorer + Context-Aware AI Chat + human-approved change proposals) |
| **Phase 4** | Day 7–8 | GitHub Integration + Meeting-to-Code Agent + Diffs + PR Proposals + Human Approval Flow |
| **Phase 5** | Day 9–10 | Sandbox Testing + Project Memory (RAG) + Polish UI + Demo Prep |

## ✅ Status — Phases 1, 2, 3, 4 & 5 are built and running

| Area | State |
|---|---|
| Monorepo, Next.js 15 web app, FastAPI API | ✅ Running |
| Auth (register/login/JWT), workspaces | ✅ Working |
| Audio upload + streaming + consent gate | ✅ Working |
| Real local STT (faster-whisper, CPU) | ✅ Verified on real speech |
| Meeting → summary/decisions/risks/questions/action items | ✅ Working |
| Offline extractive fallback (no LLM needed) | ✅ Working |
| Kanban board (drag & drop, priorities, due dates) | ✅ Working |
| Meeting Room split view (transcript ⇄ insights) | ✅ Working |
| **Editable AI output** (summary, lists, decisions CRUD) | ✅ Working |
| **Team members** (add by email, roles, remove) + assignees/avatars | ✅ Working |
| **Task filters** (search, assignee/My tasks, priority, due date) | ✅ Working |
| **Meeting history + archive + search** | ✅ Working |
| **Dev Studio sandbox** (tree, read/write/create/delete, path-escape proof) | ✅ Working |
| **Monaco editor** (local bundle, file tabs, save) + sample project | ✅ Working |
| **Context-aware AI chat** (open file + file tree + linked meeting/task) | ✅ Working |
| **Offline static analyzer** (lint, TODO scan, structure, no LLM needed) | ✅ Working |
| **Change proposals** (diff review → approve writes / reject discards) | ✅ Working |
| **Meeting→Code agent** (decisions → requirements, subtasks, affected files) | ✅ Working |
| **Plan → proposals** (apply a plan into pending, reviewable changes) | ✅ Working |
| **Local git provider** (init, status, diff, log, branch, commit, merge) | ✅ Working |
| **Repository connections** (offline local sandbox + GitHub metadata) | ✅ Working |
| **Pull-request proposals** (draft snapshot → open commit → merge / close) | ✅ Working |
| **GitHub push** (blobs → tree → commit → pull request via REST) | ✅ Gated on `GITHUB_TOKEN` |
| **Sandbox test runs** (bundled offline runner, fail → fix → pass) | ✅ Working |
| **Project Memory (RAG)** (offline embeddings, index → search → clear) | ✅ Working |

**Test suites: 435 checks, all passing** — `smoke`, `normalize`, `llm_providers`, `fallback`, `pipeline`, `fallback_pipeline`, `team`, `studio`, `ship`, `verify`, `memory`.
Live HTTP verification: `verify_live_stack.py` (11/11), `verify_live_phase2.py` (16/16), `verify_live_phase3.py` (21/21), `verify_live_phase4.py` (26/26) and `verify_live_phase5.py` (26/26).

## ☁️ Deploy it live (no localhost)

Want a public URL that runs entirely in the cloud — no PC, no Ollama? See
**[docs/DEPLOY.md](docs/DEPLOY.md)** for a step-by-step, all-free-tier guide:

- **Web + API + Postgres → Vercel** (one project, Services mode — `vercel.json`)
- **AI → Google Gemini** (one free key: LLM + speech-to-text + embeddings)

Config is only environment variables — the local setup below keeps working unchanged.

## 🚦 Quickstart

Prerequisites: **Node 20+** and **Python 3.11+**. Docker, Ollama and API keys are all *optional* — the app runs on SQLite + offline extraction out of the box.

### 1. Start the API (FastAPI, port 8000)

```powershell
# one-time setup
python -m venv apps\api\venv
apps\api\venv\Scripts\pip install -r apps\api\requirements.txt

# run
powershell -ExecutionPolicy Bypass -File scripts\start-api.ps1
# or manually:
cd apps\api ; .\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

- Health: <http://127.0.0.1:8000/health>
- Swagger: <http://127.0.0.1:8000/docs>
- A `syncforge.db` file is created automatically on first run (no DB server needed).

### 2. Start the web app (Next.js, port 3000)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-web.ps1
# or manually:
cd apps\web ; npx next dev
```

Open <http://localhost:3000> → **Get Started** → create an account → upload a meeting.

Then open **Dev Studio** in the sidebar → **Create sample project** to try the full loop:
open `src/calculator.py`, ask the AI to *"fix the divide by zero bug"*, review the
side-by-side diff, and press **Approve & write**. The AI never writes on its own.

To see the whole pipeline, open **Meeting → Code**:

1. Pick a meeting (its decisions drive the plan) and press **Generate plan**.
2. Press **Create change proposals**, then approve them inline (or in Dev Studio).
3. In **Ship it**, connect the **local sandbox** repository, press **Create draft**,
   then **Open** → **Merge**. That is a real git branch, commit and merge in the
   sandbox — entirely offline, no account required.
4. Connect a GitHub `owner/repo` instead to push the same reviewed snapshot as a
   real pull request (set `GITHUB_TOKEN` to enable it).

> Monaco is vendored into `apps/web/public/monaco` by `scripts/copy-monaco.mjs`
> (run automatically by `start-web.ps1` and `npm run dev`/`build`), so the editor
> works with no internet access and no CDN.

### 3. Run the tests

```powershell
cd apps\api
.\venv\Scripts\python.exe tests\run_all.py
```

Optional deeper checks:

```powershell
.\venv\Scripts\python.exe tests\verify_live_stack.py              # live HTTP contract (Phase 1)
.\venv\Scripts\python.exe tests\verify_live_phase2.py            # live HTTP contract (Phase 2: team/filters/edit)
.\venv\Scripts\python.exe tests\verify_live_phase3.py            # live HTTP contract (Phase 3: studio files/chat/proposals)
.\venv\Scripts\python.exe tests\verify_live_phase4.py            # live HTTP contract (Phase 4: git, PR proposals, agent)
.\venv\Scripts\python.exe tests\verify_live_phase5.py            # live HTTP contract (Phase 5: test runs, memory RAG)
.\venv\Scripts\python.exe tests\test_stt_live.py                  # real Whisper run (downloads ~75 MB)
.\venv\Scripts\python.exe tests\verify_live_e2e.py                # full live pipeline (needs API running)
.\venv\Scripts\python.exe tests\make_sample_audio.ps1             # generate sample-meeting.wav via Windows TTS
```

> **First transcription downloads the Whisper model** (`WHISPER_MODEL=small`, ~460 MB) and caches it at `~/.cache/huggingface`. Set `WHISPER_MODEL=tiny` in `apps\api\.env` for the fastest (lower quality) run.

### 4. Add AI — real LLM output

The provider ladder is **Gemini → OpenRouter → Ollama**. The simplest way to get
real AI (cloud, free, nothing to install) is a Google AI Studio key:

```powershell
# apps\api\.env
GEMINI_API_KEY=your-gemini-key      # https://aistudio.google.com/apikey
GEMINI_MODEL=gemini-2.0-flash
```

That's it — the API picks it up automatically. Other providers:

| Want | Set in `apps\api\.env` |
|---|---|
| Cloud STT (same Gemini key) | `STT_ENGINE=gemini` (auto on Vercel) |
| Faster local STT | `STT_ENGINE=whisper_local` + `pip install -r requirements-dev.txt` |
| Cloud LLM fallback | `OPENROUTER_API_KEY=sk-or-v1-...` |
| Fully local LLM (offline) | Install [Ollama](https://ollama.com/) then `ollama pull llama3.1:8b` |
| Reorder the ladder | `LLM_PROVIDER_ORDER=openrouter,gemini,ollama` |
| Nothing installed | Everything still works — the **offline extractive fallback** produces a summary, decisions, risks, questions and tasks. The summary is clearly labelled with a ⚠️ notice. Set `ALLOW_EXTRACTIVE_FALLBACK=false` to fail loudly instead. |

### Environment

Copy `.env.example` → `apps\api\.env`. The important keys:

```ini
DATABASE_URL=sqlite:///./syncforge.db   # dev default; use postgres+pgvector in prod
STT_ENGINE=whisper_local                # or gemini (cloud, same key as the LLM)
WHISPER_MODEL=small                     # tiny | base | small | medium | large-v3
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_SUMMARY_MODEL=llama3.1:8b
ALLOW_EXTRACTIVE_FALLBACK=true

# Dev Studio sandbox (per-workspace code trees live here; git-ignored)
DEVSTUDIO_ROOT=./devstudio           # default; relative to apps/api
DEVSTUDIO_MAX_FILE_KB=512            # per-file editor limit

# Ship it (Phase 4)
GITHUB_TOKEN=                        # optional: enables real GitHub pull requests
AGENT_MAX_FILES=8                    # files the Meeting→Code agent may surface
AGENT_CONTEXT_CHARS=20000            # file content fed to the planner
```

## 🧠 Design Principles

- **Human-in-the-loop** – No auto-commits, no auto-deploys. Every AI code change requires explicit user approval.
- **Safety-first** – Sandboxed execution, least-privilege repo access (PR-propose only), PII-aware processing.
- **Hinglish-first** – Optimized for Indian student teams & startups while staying English-compatible.
- **Pragmatic MVP** – Ship demo-worthy features fast, scale later. Focus on integration over building a full IDE from scratch.
- **Structured AI** – Strict JSON schemas (Pydantic + Instructor) for all LLM outputs to prevent UI/flow breakage.

## 📄 License

MIT (to be added later as per project needs)

## 👨‍💻 Author

Built for hackathons, college projects and AI-powered engineering teams.