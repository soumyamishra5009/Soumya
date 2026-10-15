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
| Summaries / extraction | Balanced | `llama-3.3:70b` |
| Fast utilities | Light | `llama-3.1:8b` |
| Code generation / agent | Code-specialized | `qwen2.5-coder:7b`, `deepseek-coder:6.7b` |

`ENABLE_MODEL_ROUTING=true` lets the API pick the cheapest model that satisfies the task.

## Security & Privacy

- Participant consent flag enforced for recordings (`REQUIRE_CONSENT_FOR_RECORDINGS`).
- Sandbox execution is isolated with CPU/memory/time limits.
- Secrets (tokens, keys) are never sent to the LLM.
- Rate limiting and audit logs on all mutating endpoints.
