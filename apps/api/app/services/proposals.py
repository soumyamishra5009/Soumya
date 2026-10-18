"""Shared helper for building human-approved code-change proposals.

Both the Dev Studio (single file, on demand) and the Meeting→Code agent (many
files, from a plan) need to turn an instruction into a :class:`CodeProposal`
with the same safety rules: sandbox-contained path, size cap, a ``base_hash``
that lets approval detect drift, and honest ``source`` labelling.

Nothing here writes to disk — it only *builds* the proposal row.
"""

from __future__ import annotations

from app.core.config import settings
from app.models.code import CodeProposal
from app.models.enums import ProposalStatus
from app.services import devstudio


class ProposalError(ValueError):
    """Raised when a proposal cannot be built (bad path, too large, ...)."""


def current_content(workspace_id: str, rel_path: str, db=None) -> str | None:
    """Read a sandbox file for hashing, ignoring the editor size limit."""
    from app.services.devstudio import _store

    return _store(db).read_content(workspace_id, rel_path)


def build_code_proposal(
    workspace_id: str,
    file_path: str,
    instruction: str,
    *,
    meeting_id: str | None = None,
    task_id: str | None = None,
    created_by: str | None = None,
    meeting_context: str | None = None,
    task_context: str | None = None,
    db=None,
) -> CodeProposal:
    """Ask the AI to propose a change to one file. Returns an unsaved model."""
    try:
        rel = devstudio.normalize_rel(file_path)
    except devstudio.SandboxError as exc:
        raise ProposalError(str(exc)) from exc

    original = current_content(workspace_id, rel, db=db)
    language = devstudio.language_for(rel)

    result = devstudio.ai_code_proposal(
        rel,
        instruction,
        content=original,
        language=language,
        meeting_context=meeting_context,
        task_context=task_context,
    )

    proposed = result.get("proposed_content") or ""
    if len(proposed.encode("utf-8")) > devstudio.max_file_bytes():
        raise ProposalError(
            f"Proposed contents for {rel} exceed the "
            f"{settings.DEVSTUDIO_MAX_FILE_KB} KB file limit"
        )

    added, removed = devstudio.diff_stats(original, proposed)
    return CodeProposal(
        workspace_id=workspace_id,
        file_path=rel,
        language=language,
        original_content=original,
        proposed_content=proposed,
        rationale=result.get("rationale"),
        source=result.get("source", "fallback"),
        status=ProposalStatus.PENDING.value,
        base_hash=devstudio.content_hash(original),
        added_lines=added,
        removed_lines=removed,
        meeting_id=meeting_id,
        task_id=task_id,
        created_by=created_by,
    )
