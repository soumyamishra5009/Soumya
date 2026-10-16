"""Dev Studio endpoints (Phase 3).

A sandboxed, per-workspace code tree with context-aware AI chat and
human-approved change proposals. The AI never writes to disk: a proposal must
be explicitly approved by a workspace member before it is applied.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.code import CodeProposal
from app.models.enums import ProposalStatus
from app.models.meeting import Meeting
from app.models.task import Task
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.code import (
    ChatSuggestion,
    CodeProposalOut,
    EntryOut,
    FileCreateRequest,
    FileWriteRequest,
    LintResult,
    ProposalCreateRequest,
    ProposalDecisionOut,
    SeedResult,
    StudioChatRequest,
    StudioChatResponse,
    StudioFile,
    StudioTree,
)
from app.services import devstudio

logger = logging.getLogger(__name__)

router = APIRouter(tags=["studio"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _assert_member(db: Session, workspace_id: str, user: User) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )
    if member is None and workspace.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return workspace


def _sandbox_error(exc: devstudio.SandboxError) -> HTTPException:
    message = str(exc)
    code = 400
    if "escapes" in message or "traversal" in message or "Absolute" in message:
        code = 400
    return HTTPException(status_code=code, detail=message)


def _meeting_context(db: Session, meeting_id: str | None, user: User) -> str | None:
    if not meeting_id:
        return None
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        return None
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == meeting.workspace_id,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )
    if member is None:
        workspace = db.get(Workspace, meeting.workspace_id)
        if workspace is None or workspace.owner_id != user.id:
            return None
    lines = [f"Title: {meeting.title}"]
    if meeting.meeting_date:
        lines.append(f"Date: {meeting.meeting_date}")
    if meeting.summary:
        lines.append(f"Summary: {meeting.summary}")
    if meeting.key_points:
        lines.append("Key points: " + "; ".join(str(p) for p in meeting.key_points[:8]))
    if meeting.next_steps:
        lines.append("Next steps: " + "; ".join(str(p) for p in meeting.next_steps[:8]))
    decisions = getattr(meeting, "decisions", None) or []
    if decisions:
        lines.append(
            "Decisions: "
            + "; ".join(f"{d.title} ({d.impact})" for d in decisions[:8])
        )
    return "\n".join(lines)[:4000]


def _task_context(db: Session, task_id: str | None, user: User) -> str | None:
    if not task_id:
        return None
    task = db.get(Task, task_id)
    if task is None:
        return None
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == task.workspace_id,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )
    if member is None:
        workspace = db.get(Workspace, task.workspace_id)
        if workspace is None or workspace.owner_id != user.id:
            return None
    lines = [
        f"Title: {task.title}",
        f"Status: {task.status} · Priority: {task.priority}",
    ]
    if task.description:
        lines.append(f"Details: {task.description}")
    if task.due_date:
        lines.append(f"Due: {task.due_date}")
    return "\n".join(lines)[:2000]


def _current_content(workspace_id: str, rel_path: str) -> str | None:
    """Read the file ignoring editor limits (used for hash comparison)."""
    path, _ = devstudio.resolve_path(workspace_id, rel_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _get_proposal(db: Session, workspace_id: str, proposal_id: str) -> CodeProposal:
    proposal = db.get(CodeProposal, proposal_id)
    if proposal is None or proposal.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


# --------------------------------------------------------------------------
# Tree / files
# --------------------------------------------------------------------------


@router.get("/workspaces/{workspace_id}/studio/tree", response_model=StudioTree)
def get_tree(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StudioTree:
    _assert_member(db, workspace_id, user)
    return StudioTree(**devstudio.list_tree(workspace_id))


@router.post(
    "/workspaces/{workspace_id}/studio/seed",
    response_model=SeedResult,
    status_code=status.HTTP_201_CREATED,
)
def seed_project(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SeedResult:
    """Create the bundled sample project (skips files that already exist)."""
    _assert_member(db, workspace_id, user)
    created = devstudio.seed_sample(workspace_id)
    total = len(devstudio.SAMPLE_FILES)
    return SeedResult(created=created, skipped=total - len(created))


@router.get(
    "/workspaces/{workspace_id}/studio/files/{path:path}",
    response_model=StudioFile,
)
def get_file(
    workspace_id: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StudioFile:
    _assert_member(db, workspace_id, user)
    try:
        return StudioFile(**devstudio.read_file(workspace_id, path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except devstudio.SandboxError as exc:
        raise _sandbox_error(exc)


@router.put(
    "/workspaces/{workspace_id}/studio/files/{path:path}",
    response_model=StudioFile,
)
def put_file(
    workspace_id: str,
    path: str,
    payload: FileWriteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StudioFile:
    """Save a file (creates it and any parent directories if needed)."""
    _assert_member(db, workspace_id, user)
    try:
        return StudioFile(**devstudio.write_file(workspace_id, path, payload.content))
    except devstudio.SandboxError as exc:
        raise _sandbox_error(exc)


@router.post(
    "/workspaces/{workspace_id}/studio/files",
    response_model=EntryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_entry(
    workspace_id: str,
    payload: FileCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EntryOut:
    _assert_member(db, workspace_id, user)
    try:
        if payload.kind == "dir":
            return EntryOut(**devstudio.create_dir(workspace_id, payload.path))
        result = devstudio.create_file(workspace_id, payload.path, payload.content)
        return EntryOut(path=result["path"], name=result["name"], type="file")
    except devstudio.SandboxError as exc:
        raise _sandbox_error(exc)


@router.delete(
    "/workspaces/{workspace_id}/studio/files/{path:path}",
    response_model=EntryOut,
)
def delete_entry(
    workspace_id: str,
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EntryOut:
    _assert_member(db, workspace_id, user)
    try:
        return EntryOut(**devstudio.delete_entry(workspace_id, path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Path not found")
    except devstudio.SandboxError as exc:
        raise _sandbox_error(exc)


@router.post(
    "/workspaces/{workspace_id}/studio/lint",
    response_model=LintResult,
)
def lint_file(
    workspace_id: str,
    payload: FileWriteRequest,
    path: str = Query(..., description="Sandbox-relative path of the file."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LintResult:
    """Run the offline linter on the *current editor buffer* of a file."""
    _assert_member(db, workspace_id, user)
    try:
        rel = devstudio.normalize_rel(path)
    except devstudio.SandboxError as exc:
        raise _sandbox_error(exc)
    language = devstudio.language_for(rel)
    findings = devstudio.static_lint(payload.content, language, rel)
    return LintResult(path=rel, language=language, findings=findings)


# --------------------------------------------------------------------------
# AI chat
# --------------------------------------------------------------------------


@router.post(
    "/workspaces/{workspace_id}/studio/chat",
    response_model=StudioChatResponse,
)
def studio_chat(
    workspace_id: str,
    payload: StudioChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StudioChatResponse:
    """Context-aware assistant: aware of the open file, the file tree, and an
    optionally linked meeting or task."""
    _assert_member(db, workspace_id, user)

    tree = devstudio.list_tree(workspace_id)
    file_path: str | None = None
    file_content: str | None = None
    language = "plaintext"
    if payload.file_path:
        try:
            rel = devstudio.normalize_rel(payload.file_path)
            language = devstudio.language_for(rel)
            file_path = rel
            file_content = _current_content(workspace_id, rel)
        except devstudio.SandboxError:
            file_path = None

    meeting_ctx = _meeting_context(db, payload.meeting_id, user)
    task_ctx = _task_context(db, payload.task_id, user)

    result = devstudio.ai_code_answer(
        payload.message,
        history=[t.model_dump() for t in payload.history],
        tree=tree,
        file_path=file_path,
        file_content=file_content,
        language=language,
        meeting_context=meeting_ctx,
        task_context=task_ctx,
    )

    return StudioChatResponse(
        answer=result["answer"],
        source=result["source"],
        suggestions=[ChatSuggestion(**s) for s in result.get("suggestions", [])],
        context_used={
            "file_path": file_path,
            "file_lines": len(file_content.splitlines()) if file_content else 0,
            "files_in_workspace": len(devstudio.flatten_paths(tree, 500)),
            "meeting_linked": meeting_ctx is not None,
            "task_linked": task_ctx is not None,
        },
        fallback_reason=result.get("fallback_reason"),
    )


# --------------------------------------------------------------------------
# Change proposals (human-in-the-loop)
# --------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/studio/proposals",
    response_model=list[CodeProposalOut],
)
def list_proposals(
    workspace_id: str,
    proposal_status: str | None = Query(
        default=None, alias="status", description="pending | approved | rejected"
    ),
    file_path: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CodeProposal]:
    _assert_member(db, workspace_id, user)
    query = db.query(CodeProposal).filter(CodeProposal.workspace_id == workspace_id)
    if proposal_status:
        query = query.filter(CodeProposal.status == proposal_status)
    if file_path:
        query = query.filter(CodeProposal.file_path == file_path)
    return query.order_by(CodeProposal.created_at.desc()).limit(min(limit, 500)).all()


@router.post(
    "/workspaces/{workspace_id}/studio/proposals",
    response_model=CodeProposalOut,
    status_code=status.HTTP_201_CREATED,
)
def create_proposal(
    workspace_id: str,
    payload: ProposalCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CodeProposal:
    """Ask the AI to propose a change. Nothing is written to disk here."""
    _assert_member(db, workspace_id, user)

    try:
        rel = devstudio.normalize_rel(payload.file_path)
    except devstudio.SandboxError as exc:
        raise _sandbox_error(exc)

    original = _current_content(workspace_id, rel)
    language = devstudio.language_for(rel)

    result = devstudio.ai_code_proposal(
        rel,
        payload.instruction,
        content=original,
        language=language,
        meeting_context=_meeting_context(db, payload.meeting_id, user),
        task_context=_task_context(db, payload.task_id, user),
    )

    proposed = result["proposed_content"]
    if len(proposed.encode("utf-8")) > devstudio.max_file_bytes():
        raise HTTPException(
            status_code=413,
            detail=(
                "Proposed contents exceed the "
                f"{settings.DEVSTUDIO_MAX_FILE_KB} KB file limit"
            ),
        )

    added, removed = devstudio.diff_stats(original, proposed)
    proposal = CodeProposal(
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
        meeting_id=payload.meeting_id,
        task_id=payload.task_id,
        created_by=user.id,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.get(
    "/workspaces/{workspace_id}/studio/proposals/{proposal_id}",
    response_model=CodeProposalOut,
)
def get_proposal(
    workspace_id: str,
    proposal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CodeProposal:
    _assert_member(db, workspace_id, user)
    return _get_proposal(db, workspace_id, proposal_id)


@router.post(
    "/workspaces/{workspace_id}/studio/proposals/{proposal_id}/approve",
    response_model=ProposalDecisionOut,
)
def approve_proposal(
    workspace_id: str,
    proposal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProposalDecisionOut:
    """Apply an approved proposal to the sandbox (the only write path)."""
    _assert_member(db, workspace_id, user)
    proposal = _get_proposal(db, workspace_id, proposal_id)

    if proposal.status != ProposalStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=f"This proposal was already {proposal.status}",
        )

    current = _current_content(workspace_id, proposal.file_path)
    if proposal.base_hash and devstudio.content_hash(current) != proposal.base_hash:
        raise HTTPException(
            status_code=409,
            detail=(
                "The file changed after this proposal was created. "
                "Reject it and ask for a fresh proposal."
            ),
        )

    try:
        written = devstudio.write_file(
            workspace_id, proposal.file_path, proposal.proposed_content
        )
    except devstudio.SandboxError as exc:
        raise _sandbox_error(exc)

    proposal.status = ProposalStatus.APPROVED.value
    proposal.decided_at = datetime.now(timezone.utc)
    proposal.decided_by = user.id
    db.commit()
    db.refresh(proposal)

    return ProposalDecisionOut(
        proposal=CodeProposalOut.model_validate(proposal),
        applied=True,
        message=f"Applied to {written['path']} ({written['size']} bytes).",
    )


@router.post(
    "/workspaces/{workspace_id}/studio/proposals/{proposal_id}/reject",
    response_model=ProposalDecisionOut,
)
def reject_proposal(
    workspace_id: str,
    proposal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProposalDecisionOut:
    """Discard a proposal. The sandbox is left untouched."""
    _assert_member(db, workspace_id, user)
    proposal = _get_proposal(db, workspace_id, proposal_id)

    if proposal.status != ProposalStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=f"This proposal was already {proposal.status}",
        )

    proposal.status = ProposalStatus.REJECTED.value
    proposal.decided_at = datetime.now(timezone.utc)
    proposal.decided_by = user.id
    db.commit()
    db.refresh(proposal)

    return ProposalDecisionOut(
        proposal=CodeProposalOut.model_validate(proposal),
        applied=False,
        message="Proposal rejected — the file was not changed.",
    )
