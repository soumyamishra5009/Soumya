# SyncForge AI

> An AI-powered workspace that automates the entire flow: **Meetings → Decisions → Tasks → Code → Verification**

## 🚀 Vision

SyncForge AI bridges the gap between discussions and execution. Instead of meeting notes getting lost, it extracts actionable decisions, converts them into trackable tasks, and helps implement them directly through an AI coding agent — all inside one unified workspace.

## ✨ Key Features

| Feature | Description |
|---|---|
| **AI Meeting Intelligence** | Upload audio/meetings and get transcripts with speaker timestamps, summaries, key decisions, action items, risks and unanswered questions. Supports English + Hinglish. |
| **Smart Action Tracker** | Auto-generated tasks linked to their source meeting. Kanban board (To Do, In Progress, Review, Done) with assignees, priorities, due dates and overdue alerts. |
| **Meeting-to-Code Agent** | Converts meeting decisions into technical requirements, breaks them into subtasks, identifies relevant files and proposes code changes as diffs with human approval. |
| **AI Dev Studio** | Browser-based coding workspace with Monaco Editor, File Explorer, context-aware AI Chat (aware of Meeting + Task + Codebase) and diff viewer. |
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
| **Auth** | JWT (bcrypt) issued by the FastAPI | Phase 1 — OAuth via Auth.js lands with Phase 2 |
| **STT** | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (local, free) or [Groq Whisper](https://groq.com/) | Local = 0 cost, Cloud = faster fallback |
| **LLMs** | [Ollama](https://ollama.com/) (Llama 3.1, Qwen 2.5 Coder) + [OpenRouter](https://openrouter.ai/) fallback + **offline extractive fallback** | Free-first; works with *no* AI service |
| **Queue/Worker** | [Celery](https://docs.celeryq.dev/) + [Redis](https://redis.io/) | Background jobs (transcription, agent runs) |
| **Code Execution** | [Judge0 CE](https://github.com/judge0/judge0) (Docker) or [E2B](https://e2b.dev/) | Sandboxed, isolated execution |
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
| **Phase 2** | Day 3–4 | Kanban Board + Meeting→Task Linking + Editable AI Outputs + Meeting History |
| **Phase 3** | Day 5–6 | AI Dev Studio (Monaco + File Explorer + Context-Aware AI Chat) |
| **Phase 4** | Day 7–8 | GitHub Integration + Meeting-to-Code Agent + Diffs + PR Proposals + Human Approval Flow |
| **Phase 5** | Day 9–10 | Sandbox Testing + Project Memory (RAG) + Polish UI + Demo Prep |

## ✅ Status — Phase 1 is built and running

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
| Dev Studio, meeting→code agent, GitHub PRs, sandbox | 🗺 Phase 3–4 |

**Test suites: 130 checks, all passing** — `smoke`, `normalize`, `fallback`, `pipeline`, `fallback_pipeline`.

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

### 3. Run the tests

```powershell
cd apps\api
.\venv\Scripts\python.exe tests\run_all.py
```

Optional deeper checks:

```powershell
.\venv\Scripts\python.exe tests\verify_live_stack.py              # live HTTP contract
.\venv\Scripts\python.exe tests\test_stt_live.py                  # real Whisper run (downloads ~75 MB)
.\venv\Scripts\python.exe tests\verify_live_e2e.py                # full live pipeline (needs API running)
.\venv\Scripts\python.exe tests\make_sample_audio.ps1             # generate sample-meeting.wav via Windows TTS
```

> **First transcription downloads the Whisper model** (`WHISPER_MODEL=small`, ~460 MB) and caches it at `~/.cache/huggingface`. Set `WHISPER_MODEL=tiny` in `apps\api\.env` for the fastest (lower quality) run.

### 4. Add AI (optional, recommended)

```powershell
# Install Ollama, then:
ollama pull llama3.1:8b
```

That's it — the API picks it up automatically. Other providers:

| Want | Set in `apps\api\.env` |
|---|---|
| Faster cloud STT | `STT_ENGINE=groq_whisper` + `GROQ_API_KEY=...` |
| Cloud LLM without Ollama | `OPENROUTER_API_KEY=sk-or-v1-...` |
| Nothing installed | Everything still works — the **offline extractive fallback** produces a summary, decisions, risks, questions and tasks. The summary is clearly labelled with a ⚠️ notice. Set `ALLOW_EXTRACTIVE_FALLBACK=false` to fail loudly instead. |

### Environment

Copy `.env.example` → `apps\api\.env`. The important keys:

```ini
DATABASE_URL=sqlite:///./syncforge.db   # dev default; use postgres+pgvector in prod
STT_ENGINE=whisper_local                # or groq_whisper
WHISPER_MODEL=small                     # tiny | base | small | medium | large-v3
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_SUMMARY_MODEL=llama3.1:8b
ALLOW_EXTRACTIVE_FALLBACK=true
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