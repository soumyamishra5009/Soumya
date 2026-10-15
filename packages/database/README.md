# @syncforge/database

Shared database package: schemas, migrations and seed data for SyncForge AI.

- **Engine:** PostgreSQL 16 + `pgvector`
- **Migrations:** Alembic (Python, lives in `apps/api/alembic`) *or* Prisma (TS) — decision pending.
- **Planned tables (Phase 1):** `users`, `accounts`, `sessions`, `workspaces`, `workspace_members`, `meetings`, `transcripts`, `transcript_segments`, `decisions`, `tasks`, `documents`, `embeddings`.
- **Planned tables (Phase 2+):** `agent_runs`, `agent_steps`, `code_changes`, `executions`, `repositories`, `comments`, `activity_log`.

> This package currently holds shared SQL/schema assets. As soon as the ORM choice is finalized we will
> generate typed clients here and re-export them as `@syncforge/database`.

## Core relationships (planned)

```
User ─┬─< WorkspaceMember >─ Workspace
      │
      └─< Task (assignee / reporter)

Workspace ─< Meeting ─< Transcript ─< TranscriptSegment
Meeting ─< Decision
Meeting ─< Task                (traceability: which meeting produced this task)
Task ─< AgentRun ─< CodeChange
Repository ─< CodeChange
Document / Transcript / CodeFile ─< Embedding (pgvector, 768-dim)
```
