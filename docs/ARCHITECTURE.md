# SyncForge AI - Architecture

## High-Level Flow

```text
                    ┌─────────────────────────────────────────┐
                    │            apps/web (Next.js)            │
                    │  Dashboard · Meeting Room · Kanban       │
                    │  Dev Studio (Monaco) · Memory Search     │
                    └───────────────────┬─────────────────────┘
                                        │ REST / SSE
                                        ▼
                    ┌─────────────────────────────────────────┐
                    │           apps/api (FastAPI)             │
                    │  Auth · Routes · Validation · Orchestration
                    └───────────────────┬─────────────────────┘
                                        │
        ┌───────────────┬───────────────┼───────────────┬───────────────┐
        ▼               ▼               ▼               ▼               ▼
   ┌─────────┐    ┌──────────┐    ┌───────────┐   ┌──────────┐   ┌──────────┐
   │  STT    │    │   LLM    │    │   RAG     │   │  GitHub  │   │ Sandbox  │
   │ Whisper │    │ Ollama / │    │ pgvector  │   │   API    │   │  Judge0  │
   │  local  │    │OpenRouter│    │  search   │   │  PR/diff │   │   /E2B   │
   └─────────┘    └──────────┘    └───────────┘   └──────────┘   └──────────┘
        │               │               │               │               │
        └───────────────┴───────────────┼───────────────┴───────────────┘
                                        ▼
                    ┌─────────────────────────────────────────┐
                    │      PostgreSQL (data) + Redis/Celery    │
                    │      long-running jobs & vector store    │
                    └─────────────────────────────────────────┘
```

## Core Pipeline: Meeting → Code

1. **Upload** — User uploads audio/video to `/meetings/{id}/upload`.
2. **Transcribe** — Celery job runs `faster-whisper`, produces timed segments + speaker labels.
3. **Extract** — LLM (`instructor` + Pydantic schema) extracts summary, decisions, action items, risks, questions.
4. **Track** — Action items become `Task` rows linked to the `Meeting` (traceability).
5. **Plan** — Meeting-to-Code Agent converts a `Decision` into technical requirements + subtasks + affected files.
6. **Change** — Agent proposes diffs (tool calling: read_file/edit_file/search_code) — never auto-commits.
7. **Verify** — Sandbox runs generated tests; results attached to the run.
8. **Approve** — Human approves; PR is opened on GitHub with the proposed changes.

## Agent Design (Tool Calling)

| Tool | Purpose |
|---|---|
| `list_files` / `read_file` | Understand the repo |
| `search_code` | Find relevant symbols |
| `edit_file` / `write_file` | Propose changes (produce diffs, not writes) |
| `run_tests` / `run_command` | Sandboxed verification |
| `create_task` | Create follow-up work items |
| `create_pr` | Open pull request (requires approval) |

**Rules:**
- Agent output is always a *proposal* until a human approves.
- Repositories are read-only by default; write access is scoped to PR proposals.
- All agent runs are logged with inputs, tool calls and outputs (audit trail).

## RAG / Project Memory

- Chunks from transcripts, documents and code files are embedded (`nomic-embed-text`, 768-dim) and stored in pgvector.
- Queries retrieve top-k chunks with similarity ≥ `SIMILARITY_THRESHOLD`.
- Answers always cite the source (meeting timestamp or file/line range).

## Model Routing (Cost-Aware)

| Task | Model Tier | Example |
|---|---|---|
| Transcription | STT (local) | faster-whisper `small` / `int8` |
| Summaries / extraction | Balanced | `llama3.1:8b` |
| Fast utilities | Light | `llama3.1:8b` |
| Code generation / agent | Code-specialized | `qwen2.5-coder:7b`, `deepseek-coder:6.7b` |

`ENABLE_MODEL_ROUTING=true` lets the API pick the cheapest model that satisfies the task.

## Graceful Degradation (Free-First)

Every AI capability has an explicit ladder. The pipeline must never depend on a
paid service or a machine you don't control.

### Analysis ladder (`extract_meeting_intelligence`)

1. **Ollama (local)** — primary, free, `OLLAMA_BASE_URL`.
2. **OpenRouter** — cloud fallback if `OPENROUTER_API_KEY` is set.
3. **Offline extractive fallback** — heuristic analysis with no LLM at all.

If step 1/2 fails and `ALLOW_EXTRACTIVE_FALLBACK=true` (default), the extractor
switches to `fallback_extract()` in `app/services/meeting_summary.py`:

- sentence splitting → content-word frequency scoring for key points
- cue-based classification for decisions / actions / risks / questions (English **and Hinglish**)
- assignee inference from `"<Name> will/should/must …"` patterns
- due-date parsing (`ISO`, `d/m/Y`, `by Friday`, `today`, `tomorrow`, `next week`)

The result is **labelled** — `meeting.summary` is prefixed with a ⚠️ notice and
the returned dict carries `source: "llm" | "fallback"` — so users are never
misled about AI quality. Set `ALLOW_EXTRACTIVE_FALLBACK=false` to fail loudly
instead (the meeting is marked `failed` with the reason surfaced).

### Transcription ladder (`stt.transcribe_with_fallback`)

1. `whisper_local` (faster-whisper, CPU `int8`) — 0 cost
2. `groq_whisper` — only if `GROQ_API_KEY` is set
3. meeting marked `failed` with the error surfaced in the UI

### Known integration

- **PyAV compatibility**: faster-whisper ≤ 1.1.x calls `av.open(..., metadata_errors="ignore")`,
  which newer PyAV removed. `stt._install_av_compat()` wraps `av.open` to drop
  rejected keywords instead of pinning an old PyAV (Python 3.14 has no wheel for it).
- **Duration probing** (`app/services/audio.py`): WAV via stdlib `wave`, other
  containers via PyAV metadata (no full decode), so the UI shows length before
  transcription runs.

## Environment Tiers

| Concern | Dev (default) | Production |
|---|---|---|
| Database | `sqlite:///./syncforge.db` | Postgres + `pgvector` via `DATABASE_URL` |
| Background jobs | FastAPI `BackgroundTasks` | Celery + Redis |
| Storage | `./uploads` local disk | Supabase/S3-compatible |
| LLM | Offline fallback or local Ollama | Ollama or OpenRouter |
| STT | faster-whisper local | faster-whisper or Groq |

### Dev-DB schema evolution

`Base.metadata.create_all()` creates missing *tables* but never missing *columns*, so
`init_db()` also runs `_ensure_columns()` (`app/core/database.py`) — an idempotent list of
additive `ALTER TABLE … ADD COLUMN` statements (e.g. `meetings.archived`). This keeps local
SQLite zero-setup; **production uses Alembic** (`apps/api/alembic`).

## API Surface (Phase 2)

| Method | Path | Purpose |
|---|---|---|
| `GET/POST` | `/api/v1/workspaces/{id}/members` | List members / add an existing account by email |
| `DELETE` | `/api/v1/workspaces/{id}/members/{user_id}` | Remove a member (owner/admin only) |
| `GET` | `/api/v1/workspaces/{id}/tasks` | Filterable tasks: `task_status`, `assignee_id` (`me`/`unassigned`), `priority`, `q`, `meeting_id`, `due_before`, `due_after` |
| `GET` | `/api/v1/workspaces/{id}/meetings` | Meeting history: `q`, `meeting_status`, `archived` (default = active only) |
| `PATCH` | `/api/v1/meetings/{id}` | Edit metadata and **editable AI output** (summary, key points, risks, questions, next steps) + `archived` |
| `POST` | `/api/v1/meetings/{id}/decisions` | Record a decision the AI missed |
| `PATCH/DELETE` | `/api/v1/decisions/{id}` | Edit / delete a decision |

Assignees are validated to be workspace members (`_assert_assignee`), and member management
requires the owner/admin role. Re-processing a meeting regenerates its AI-derived decisions
and tasks (human edits to those rows are intentionally overwritten).

## API Auth & Media

- Phase 1 uses **JWT issued by FastAPI** (`bcrypt` + HS256), sent as `Authorization: Bearer`.
- Workspace access is enforced by `require_workspace_member`-style guards on every endpoint.
- `GET /api/v1/meetings/{id}/audio` accepts the token either as a bearer header **or**
  `?token=…`, because HTML `<audio>` elements cannot set custom headers.
  It returns 404 when no file is stored, 403 for non-members.

## Security & Privacy

- Participant consent flag enforced for recordings (`REQUIRE_CONSENT_FOR_RECORDINGS`).
- Sandbox execution is isolated with CPU/memory/time limits.
- Secrets (tokens, keys) are never sent to the LLM.
- Rate limiting and audit logs on all mutating endpoints.
