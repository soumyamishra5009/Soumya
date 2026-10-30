# SyncForge AI - Architecture

## High-Level Flow

```text
                    ┌─────────────────────────────────────────┐
                    │            apps/web (Next.js)            │
                    │  Dashboard · Meeting Room · Kanban       │
                    │  Dev Studio (Monaco) · Meeting → Code    │
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
   │ Whisper │    │ Gemini / │    │ pgvector  │   │   API    │   │  Judge0  │
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

Status legend: **✅ live** · **🗺 planned**

1. **Upload** — User uploads audio/video to `/meetings/{id}/upload`. ✅
2. **Transcribe** — `faster-whisper` produces timed segments + speaker labels. ✅
3. **Extract** — LLM (`structured_completion` + Pydantic validation) extracts summary, decisions, action items, risks, questions. ✅
4. **Track** — Action items become `Task` rows linked to the `Meeting` (traceability). ✅
5. **Plan** — Meeting-to-Code Agent converts a `Decision` into technical requirements + subtasks + affected files, then into `CodeProposal`s. ✅
6. **Change** — The Dev Studio proposes full-file edits as `CodeProposal` rows (with rationale + a Monaco diff) — never auto-commits. ✅
7. **Verify** — Sandboxed test runs execute the workspace's tests inside the Dev Studio sandbox (bundled offline runner, fail → fix → pass). ✅
8. **Ship** — Human approves; the change is written, then a real branch/commit is created and a PR is opened (local git or GitHub). ✅
9. **Remember** — Project Memory indexes meetings, decisions, tasks and code for semantic search (offline embeddings). ✅

## Meeting → Code Agent (Phase 4)

`app/services/agent.py` turns a meeting into an engineering plan. Inputs: the
meeting's summary/key-points/next-steps, its `Decision` rows and its linked
`Task` rows, plus the sandbox file tree. Output (`CodePlan`):

| Field | Meaning |
|---|---|
| `requirements` | What the meeting actually asked for (decisions first) |
| `subtasks` | Concrete steps, each tagged `code` / `test` / `docs` / `review` |
| `affected_files` | Ranked files + a human-readable `reason` |
| `proposed_changes` | `{path, instruction}` pairs → become `CodeProposal`s |

The offline planner tokenizes the meeting text (camelCase/`snake_case` aware,
English + Hinglish stop-words) and scores every sandbox file by keyword overlap
with its path and contents. *Applying* a plan only creates **pending**
proposals — the agent never writes to disk.

## Shipping — Local Git & Pull Requests (Phase 4)

`app/services/localgit.py` is the offline-first provider: `ensure_repo()` turns a
workspace sandbox into a real git repository with a baseline commit (created
lazily on first use), and approved edits then appear as ordinary working-tree
changes. A `PullRequestProposal` is a **snapshot** of that change set
(`files` + `diff` + line counts) captured when a human creates it; the local
provider refuses to open if the sandbox has drifted since (`snapshot_matches`),
mirroring the Dev Studio `base_hash` guard.

`app/services/ship.py` dispatches to one of two providers behind one interface:

| Provider | Open | Merge | Close |
|---|---|---|---|
| `local` | branch + commit in the sandbox | `git merge --no-ff` into base | checkout base + delete branch |
| `github` | blobs → tree → commit → ref, then `POST /pulls` | `PUT /pulls/{n}/merge` | `PATCH /pulls/{n}` |

The GitHub token is read from the environment **at call time** and is never
stored in the database. Without a token every remote call fails with a clear
message and the local provider keeps working.

### Agent Design (Tool Calling)

| Tool | Purpose | Status |
|---|---|---|
| `list_files` / `read_file` | Understand the repo | ✅ `devstudio.list_tree` / `read_file` |
| `search_code` | Find relevant symbols | ✅ keyword scoring in `agent.score_files` |
| `edit_file` / `write_file` | Propose changes (produce diffs, not writes) | ✅ `CodeProposal` |
| `create_task` | Create follow-up work items | ✅ tasks already linked to meetings |
| `create_pr` | Open pull request (requires approval) | ✅ `PullRequestProposal` → `…/open` |
| `run_tests` / `run_command` | Sandboxed verification | 🗺 Phase 5 |

**Rules:**
- Agent output is always a *proposal* until a human approves.
- Repositories are read-only by default; write access is scoped to PR proposals.
- All agent runs are logged with inputs, tool calls and outputs (audit trail).

## RAG / Project Memory (Phase 5)

- Chunks from meetings, decisions, tasks and sandbox code files are embedded and stored
  as JSON vectors in `memory_chunks` (SQLite dev default; pgvector-ready for prod).
- **Offline embeddings** use a deterministic hashing trick (word unigrams + char trigrams,
  L2-normalised, `MEMORY_EMBED_DIM=256`) so search works with no embedding server.
  When **Gemini** (`gemini-embedding-001`) or Ollama (`nomic-embed-text`) is reachable,
  real vectors are used instead (`source="llm"`).
- Queries retrieve top-k chunks with cosine similarity ≥ `MEMORY_MIN_SCORE`.
- Re-indexing is idempotent: unchanged chunks (by sha256) are skipped; stale chunks
  from deleted sources are removed.
- The UI labels offline results honestly (`source="fallback"`).

## Sandboxed Test Runs (Phase 5)

- `testrunner.py` executes a workspace's tests inside its Dev Studio sandbox as a plain
  subprocess — no Docker, no Judge0, no network.
- A **bundled dependency-free runner** collects `test_*` functions and
  `unittest.TestCase` classes, runs them and prints a machine-readable summary.
  This is the offline default so the feature works on a bare machine.
- When pytest is importable (`EXEC_PREFER_PYTEST=true`), it is used instead.
- Hard rules: arguments are always passed as a list (never through a shell); the child
  gets a **whitelisted** environment so workspace code can never read the API's secrets;
  a wall-clock timeout kills the run; output is captured, bounded and returned.
- `TestRun` rows record the outcome (passed/failed/error/timeout), counts, duration,
  command and output — the evidence a human reviews before shipping.

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

1. **Google Gemini (cloud)** — primary when `GEMINI_API_KEY` is set. Free tier,
   OpenAI-compatible, nothing installed locally — this is what live deploys use.
2. **OpenRouter (cloud)** — fallback if `OPENROUTER_API_KEY` is set.
3. **Ollama (local)** — offline last resort, `OLLAMA_BASE_URL`, no key needed.
4. **Offline extractive fallback** — heuristic analysis with no LLM at all.

Order is configurable with `LLM_PROVIDER_ORDER` (default `gemini,openrouter,ollama`).

If every provider fails and `ALLOW_EXTRACTIVE_FALLBACK=true` (default), the
extractor switches to `fallback_extract()` in `app/services/meeting_summary.py`:

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

1. **LLM** — the provider ladder: Gemini → OpenRouter → Ollama (`chat_completion`
   for Q&A, `structured_completion` for proposals). Results are labelled `source="llm"`.
2. **Offline deterministic fallback** — a code-aware analyser: structural overview
   (imports/classes/functions), TODO/FIXME scan, a small static linter (bare
   `except`, `== None`, mutable defaults, `eval`/`exec`, `==` in JS, long lines…),
   and scaffolding proposals that only *append/prepend comments* or write a test
   stub. Labelled `source="fallback"` and prefixed with a ⚠️ notice, so the UI is
   always honest about what produced the text.

### Meeting → Code ladder (`agent.ai_code_plan`)

The same three rungs as everything else:

1. **LLM** — `structured_completion` with `AGENT_MODEL` (Gemini → OpenRouter → Ollama).
   The model may only reference files that exist in the tree; hallucinated paths
   are dropped in `_coerce_plan` before the plan is stored.
2. **Offline deterministic planner** — keyword scoring against the file tree (no
   LLM, no network). Labelled `source="fallback"` with the reason attached.

Proposals created from a plan reuse the Dev Studio ladder via
`app/services/proposals.py` (a single shared builder), so both entry points apply
identical path-safety, size and hashing rules.

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
| LLM | Offline fallback or local Ollama | Gemini (cloud) or OpenRouter; Ollama optional |
| STT | faster-whisper local | faster-whisper or Groq |
| Dev Studio files | `./devstudio/<workspace_id>/` on local disk | Mounted volume / object store |
| Ship provider | `local` git repo in the sandbox (offline) | `github` via REST + `GITHUB_TOKEN` |

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
- The `.git` directory is managed only by the app: any path containing a `.git` segment is
  rejected by `normalize_rel`.
- The sandbox root itself can never be deleted.

### Human-in-the-loop change flow

1. `POST …/proposals` asks the AI for a change. **Nothing is written.**
2. The proposal stores `original_content`, `proposed_content`, `rationale`, `source`
   (`llm`/`fallback`), a `base_hash` (sha256 of the original) and added/removed line counts.
3. The UI shows a Monaco side-by-side diff; the reviewer approves or rejects.
4. `…/approve` re-reads the file and refuses (`409`) if its hash no longer matches
   `base_hash` — a stale proposal can never silently overwrite newer human work. Approved
   proposals are written to disk; rejected ones leave the file byte-identical.

## API Surface — Phase 4 (Ship it)

Repositories and pull-request proposals are rows in the database; the *code*
stays in the sandbox (local provider) or on GitHub (remote provider). Tokens are
never persisted.

| Method | Path | Purpose |
|---|---|---|
| `GET`/`POST` | `/api/v1/workspaces/{id}/repos` | List / connect a repository (`local` or `github`; admin only) |
| `GET`/`DELETE` | `/api/v1/workspaces/{id}/repos/{rid}` | Fetch / disconnect a connection |
| `POST` | `/api/v1/workspaces/{id}/repos/{rid}/check` | Probe the connection (git state, or the remote repo) |
| `GET` | `/api/v1/workspaces/{id}/git/status` | Branch, branches, changed files, commit count (creates the repo on first call) |
| `GET` | `/api/v1/workspaces/{id}/git/diff` | Unified diff of the working tree (untracked files included) |
| `GET` | `/api/v1/workspaces/{id}/git/log` | Recent commits |
| `GET`/`POST` | `/api/v1/workspaces/{id}/pull-requests` | List (filter by `status`) / snapshot the current changes as a **draft** |
| `GET` | `/api/v1/workspaces/{id}/pull-requests/{pid}` | Fetch one proposal (files + diff) |
| `POST` | `/api/v1/workspaces/{id}/pull-requests/{pid}/open` | **Approval** — create the real branch/commit (and PR when remote) |
| `POST` | `/api/v1/workspaces/{id}/pull-requests/{pid}/merge` | Merge an open proposal |
| `POST` | `/api/v1/workspaces/{id}/pull-requests/{pid}/close` | Close a draft/open proposal |
| `POST` | `/api/v1/workspaces/{id}/agent/plan` | Build a plan from a meeting / decision / focus |
| `GET` | `/api/v1/workspaces/{id}/agent/plans` | List plans |
| `GET` | `/api/v1/workspaces/{id}/agent/plans/{plan_id}` | Fetch one plan |
| `POST` | `/api/v1/workspaces/{id}/agent/plans/{plan_id}/apply` | Turn a plan into **pending** `CodeProposal`s |

Referencing a not-yet-approved proposal when creating a PR returns `409`; opening
a proposal whose sandbox drifted returns `502` and the proposal is persisted as
`failed` with the reason.

## API Surface — Phase 5 (Verify & Remember)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/workspaces/{id}/tests/run` | Execute the workspace's tests in the sandbox |
| `GET` | `/api/v1/workspaces/{id}/tests` | List runs (filter by `status`) |
| `GET` | `/api/v1/workspaces/{id}/tests/latest` | Most recent run |
| `GET`/`DELETE` | `/api/v1/workspaces/{id}/tests/{rid}` | Fetch / delete a run |
| `POST` | `/api/v1/workspaces/{id}/memory/index` | (Re)index meetings, decisions, tasks and code |
| `POST` | `/api/v1/workspaces/{id}/memory/search` | Semantic search across the index |
| `GET` | `/api/v1/workspaces/{id}/memory/stats` | Chunk counts, dims, embed sources |
| `GET` | `/api/v1/workspaces/{id}/memory/chunks` | List chunks (filter by `type`) |
| `DELETE` | `/api/v1/workspaces/{id}/memory/chunks/{cid}` | Delete one chunk |
| `DELETE` | `/api/v1/workspaces/{id}/memory` | Clear the index (optionally by `type`) |

Test runs return `400` for an empty sandbox, a traversal/`.git` target, or an
undetectable test setup. Memory search returns `400` for a blank query.

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
- **Git operations never touch the network** for the `local` provider: `git` runs with
  `--no-pager`, `GIT_TERMINAL_PROMPT=0`, `GIT_CONFIG_NOSYSTEM=1` and list-form arguments
  (no shell), inside `DEVSTUDIO_ROOT/<workspace_id>`. Branch names are validated and the
  `.git` directory is unreachable through the file API.
- **GitHub tokens are read from the environment at call time** and are never written to the
  database, so a database leak cannot leak a credential.
- Secrets (tokens, keys) are never sent to the LLM.
- Rate limiting and audit logs on all mutating endpoints.
