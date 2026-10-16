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

Status legend: **✅ live** · **🗺 planned (Phase 4–5)**

1. **Upload** — User uploads audio/video to `/meetings/{id}/upload`. ✅
2. **Transcribe** — `faster-whisper` produces timed segments + speaker labels. ✅
3. **Extract** — LLM (`structured_completion` + Pydantic validation) extracts summary, decisions, action items, risks, questions. ✅
4. **Track** — Action items become `Task` rows linked to the `Meeting` (traceability). ✅
5. **Plan** — Meeting-to-Code Agent converts a `Decision` into technical requirements + subtasks + affected files. 🗺
6. **Change** — The Dev Studio proposes full-file edits as `CodeProposal` rows (with rationale + a Monaco diff) — never auto-commits. ✅
7. **Verify** — Sandbox runs generated tests; results attached to the run. 🗺 (the sample project ships a failing test to demonstrate this step)
8. **Approve** — Human approves; the change is written, and (Phase 4) a PR is opened on GitHub. ✅ approval · 🗺 PR

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

### Dev Studio ladder (`devstudio.ai_code_answer` / `ai_code_proposal`)

1. **LLM** — Ollama first, then OpenRouter (`chat_completion` for Q&A,
   `structured_completion` for proposals). Results are labelled `source="llm"`.
2. **Offline deterministic fallback** — a code-aware analyser: structural overview
   (imports/classes/functions), TODO/FIXME scan, a small static linter (bare
   `except`, `== None`, mutable defaults, `eval`/`exec`, `==` in JS, long lines…),
   and scaffolding proposals that only *append/prepend comments* or write a test
   stub. Labelled `source="fallback"` and prefixed with a ⚠️ notice, so the UI is
   always honest about what produced the text.

### Known integration

- **PyAV compatibility**: faster-whisper ≤ 1.1.x calls `av.open(..., metadata_errors="ignore")`,
  which newer PyAV removed. `stt._install_av_compat()` wraps `av.open` to drop
  rejected keywords instead of pinning an old PyAV (Python 3.14 has no wheel for it).
- **Duration probing** (`app/services/audio.py`): WAV via stdlib `wave`, other
  containers via PyAV metadata (no full decode), so the UI shows length before
  transcription runs.
- **Monaco is vendored, not CDN-loaded**: `@monaco-editor/react` defaults to fetching
  Monaco from jsDelivr, which would break the Dev Studio offline. `apps/web/scripts/copy-monaco.mjs`
  copies `monaco-editor/min/vs` into `apps/web/public/monaco/vs` (git-ignored) and the page
  calls `loader.config({ paths: { vs: "/monaco/vs" } })`. The script is idempotent and runs
  from `npm run dev`/`build` and `scripts/start-web.ps1`.

## Environment Tiers

| Concern | Dev (default) | Production |
|---|---|---|
| Database | `sqlite:///./syncforge.db` | Postgres + `pgvector` via `DATABASE_URL` |
| Background jobs | FastAPI `BackgroundTasks` | Celery + Redis |
| Storage | `./uploads` local disk | Supabase/S3-compatible |
| LLM | Offline fallback or local Ollama | Ollama or OpenRouter |
| STT | faster-whisper local | faster-whisper or Groq |
| Dev Studio files | `./devstudio/<workspace_id>/` on local disk | Mounted volume / object store |

### Dev-DB schema evolution

`Base.metadata.create_all()` creates missing *tables* but never missing *columns*, so
`init_db()` also runs `_ensure_columns()` (`app/core/database.py`) — an idempotent list of
additive `ALTER TABLE … ADD COLUMN` statements (e.g. `meetings.archived`). This keeps local
SQLite zero-setup; **production uses Alembic** (`apps/api/alembic`).

## API Surface — Phase 2

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

## API Surface — Phase 3 (Dev Studio)

Files live in a per-workspace disk sandbox (`DEVSTUDIO_ROOT/<workspace_id>/`); the database
stores only change proposals (`code_proposals`) for audit.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/workspaces/{id}/studio/tree` | Nested file tree (dirs first), with size/language/editable per file |
| `GET`/`PUT` | `/api/v1/workspaces/{id}/studio/files/{path}` | Read (404 if missing) / save a text file (creates parents) |
| `POST` | `/api/v1/workspaces/{id}/studio/files` | Create a file (`kind=file`) or folder (`kind=dir`) |
| `DELETE` | `/api/v1/workspaces/{id}/studio/files/{path}` | Delete a file, or a directory recursively |
| `POST` | `/api/v1/workspaces/{id}/studio/seed` | Create the bundled sample project (skips existing files) |
| `POST` | `/api/v1/workspaces/{id}/studio/lint` | Offline static analysis of an editor buffer (`?path=…`) |
| `POST` | `/api/v1/workspaces/{id}/studio/chat` | Context-aware Q&A (`file_path`, `meeting_id`, `task_id`, `history`) |
| `GET`/`POST` | `/api/v1/workspaces/{id}/studio/proposals` | List (filter by `status`) / create a change proposal |
| `GET` | `/api/v1/workspaces/{id}/studio/proposals/{pid}` | Fetch one proposal (original ⇄ proposed + rationale) |
| `POST` | `/api/v1/workspaces/{id}/studio/proposals/{pid}/approve` | **The only write path** — applies the proposed contents |
| `POST` | `/api/v1/workspaces/{id}/studio/proposals/{pid}/reject` | Discard a proposal; the file is untouched |

### Sandbox guarantees

- Every path is normalised (`devstudio.normalize_rel`) — absolute paths, drive letters,
  `~`, NUL bytes and any `..` segment are rejected, and the resolved target must be
  `is_relative_to()` the workspace root. Traversal escapes return `400`.
- Only text/code files are readable/writable (extension + filename allow-list); dotfiles
  are denied except `.env.example`, `.gitignore`, `.dockerignore`, `.editorconfig`.
- Per-file size cap (`DEVSTUDIO_MAX_FILE_KB`), tree depth (`DEVSTUDIO_MAX_DEPTH`) and file
  count (`DEVSTUDIO_MAX_FILES`) caps keep listings bounded.
- The sandbox root itself can never be deleted.

### Human-in-the-loop change flow

1. `POST …/proposals` asks the AI for a change. **Nothing is written.**
2. The proposal stores `original_content`, `proposed_content`, `rationale`, `source`
   (`llm`/`fallback`), a `base_hash` (sha256 of the original) and added/removed line counts.
3. The UI shows a Monaco side-by-side diff; the reviewer approves or rejects.
4. `…/approve` re-reads the file and refuses (`409`) if its hash no longer matches
   `base_hash` — a stale proposal can never silently overwrite newer human work. Approved
   proposals are written to disk; rejected ones leave the file byte-identical.

## API Auth & Media

- Phase 1 uses **JWT issued by FastAPI** (`bcrypt` + HS256), sent as `Authorization: Bearer`.
- Workspace access is enforced by `require_workspace_member`-style guards on every endpoint.
- `GET /api/v1/meetings/{id}/audio` accepts the token either as a bearer header **or**
  `?token=…`, because HTML `<audio>` elements cannot set custom headers.
  It returns 404 when no file is stored, 403 for non-members.

## Security & Privacy

- Participant consent flag enforced for recordings (`REQUIRE_CONSENT_FOR_RECORDINGS`).
- Sandbox execution is isolated with CPU/memory/time limits.
- **Dev Studio file access is confined to `DEVSTUDIO_ROOT/<workspace_id>/`** — path
  traversal, absolute paths and non-text extensions are rejected, and the sandbox root is
  never deletable.
- **No AI-authored code reaches disk without explicit human approval**, and approved
  proposals are hash-checked so they cannot clobber newer edits.
- Secrets (tokens, keys) are never sent to the LLM.
- Rate limiting and audit logs on all mutating endpoints.
