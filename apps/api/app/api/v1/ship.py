"""Phase 4 endpoints: repositories, local git and pull-request proposals.

The "ship it" half of the pipeline. A change set is captured as a *draft*
proposal and only becomes a real branch/commit/PR when a human opens it — the AI
never commits, pushes or merges on its own.

The default provider is ``local``: a real git repository inside the Dev Studio
sandbox, so the whole flow works offline with no account. ``github`` pushes the
same reviewed snapshot to a remote repository through the REST API.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import (
    assert_workspace_admin,
    assert_workspace_member,
    get_current_user,
)
from app.models.code import CodeProposal
from app.models.enums import ProposalStatus, PullRequestStatus, RepoProvider
from app.models.ship import PullRequestProposal, RepoConnection
from app.models.user import User
from app.schemas.ship import (
    ChangedFileOut,
    GitCommitOut,
    GitDiffOut,
    GitStatusOut,
    PullRequestCreateRequest,
    PullRequestDecisionOut,
    PullRequestFileOut,
    PullRequestOut,
    RepoCheckOut,
    RepoConnectionCreate,
    RepoConnectionOut,
)
from app.services import githost, localgit, ship

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ship"])

MAX_DIFF_CHARS = 200_000


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _git_available() -> bool:
    return localgit.available()


def _require_git() -> None:
    if not _git_available():
        raise HTTPException(
            status_code=503,
            detail="git is not installed on the server; the local provider is unavailable",
        )


def _init_repo(db: Session, workspace_id: str, user: User) -> None:
    """Lazily create the sandbox repository (idempotent)."""
    _require_git()
    try:
        localgit.ensure_repo(
            workspace_id, author_name=user.name, author_email=user.email
        )
    except localgit.GitError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc}")


def _load_repo(db: Session, workspace_id: str, repo_id: str) -> RepoConnection:
    repo = db.get(RepoConnection, repo_id)
    if repo is None or repo.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


def _load_pr(db: Session, workspace_id: str, pr_id: str) -> PullRequestProposal:
    pr = db.get(PullRequestProposal, pr_id)
    if pr is None or pr.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Pull-request proposal not found")
    return pr


def _pr_out(pr: PullRequestProposal) -> PullRequestOut:
    files = [
        PullRequestFileOut(
            path=f.get("path", ""),
            status=f.get("status", "modified"),
            deleted=bool(f.get("deleted")),
            added_lines=int(f.get("added_lines") or 0),
            removed_lines=int(f.get("removed_lines") or 0),
        )
        for f in (pr.files or [])
        if isinstance(f, dict)
    ]
    return PullRequestOut(
        id=pr.id,
        workspace_id=pr.workspace_id,
        repo_id=pr.repo_id,
        provider=pr.provider,
        title=pr.title,
        body=pr.body,
        branch_name=pr.branch_name,
        base_branch=pr.base_branch,
        status=pr.status,
        changed_files=files,
        skipped_files=[str(s) for s in (pr.skipped_files or [])],
        diff=pr.diff,
        file_count=pr.file_count,
        added_lines=pr.added_lines,
        removed_lines=pr.removed_lines,
        commit_sha=pr.commit_sha,
        external_number=pr.external_number,
        external_url=pr.external_url,
        error=pr.error,
        meeting_id=pr.meeting_id,
        task_id=pr.task_id,
        created_by=pr.created_by,
        decided_by=pr.decided_by,
        created_at=pr.created_at,
        decided_at=pr.decided_at,
    )


# --------------------------------------------------------------------------
# Repository connections
# --------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/repos",
    response_model=list[RepoConnectionOut],
)
def list_repos(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RepoConnection]:
    assert_workspace_member(db, workspace_id, user)
    return (
        db.query(RepoConnection)
        .filter(RepoConnection.workspace_id == workspace_id)
        .order_by(RepoConnection.created_at.desc())
        .all()
    )


@router.post(
    "/workspaces/{workspace_id}/repos",
    response_model=RepoConnectionOut,
    status_code=http_status.HTTP_201_CREATED,
)
def connect_repo(
    workspace_id: str,
    payload: RepoConnectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RepoConnection:
    """Connect a workspace to a place its code can be shipped to."""
    assert_workspace_admin(db, workspace_id, user)

    if payload.provider == RepoProvider.GITHUB.value:
        try:
            full_name = githost.validate_full_name(payload.repo_full_name or "")
        except githost.GitHubError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        default_branch = payload.default_branch or "main"
        name = payload.name or full_name
    else:
        full_name = None
        default_branch = payload.default_branch or "main"
        name = payload.name or "Local sandbox"

    duplicate = (
        db.query(RepoConnection)
        .filter(
            RepoConnection.workspace_id == workspace_id,
            RepoConnection.provider == payload.provider,
            RepoConnection.repo_full_name == full_name,
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="This repository is already connected")

    repo = RepoConnection(
        workspace_id=workspace_id,
        provider=payload.provider,
        name=name,
        repo_full_name=full_name,
        default_branch=default_branch,
        created_by=user.id,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@router.get(
    "/workspaces/{workspace_id}/repos/{repo_id}",
    response_model=RepoConnectionOut,
)
def get_repo(
    workspace_id: str,
    repo_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RepoConnection:
    assert_workspace_member(db, workspace_id, user)
    return _load_repo(db, workspace_id, repo_id)


@router.delete(
    "/workspaces/{workspace_id}/repos/{repo_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
def delete_repo(
    workspace_id: str,
    repo_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    assert_workspace_admin(db, workspace_id, user)
    repo = _load_repo(db, workspace_id, repo_id)
    db.delete(repo)
    db.commit()


@router.post(
    "/workspaces/{workspace_id}/repos/{repo_id}/check",
    response_model=RepoCheckOut,
)
def check_repo(
    workspace_id: str,
    repo_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RepoCheckOut:
    """Verify the connection: local git state, or the remote repository."""
    assert_workspace_member(db, workspace_id, user)
    repo = _load_repo(db, workspace_id, repo_id)

    if repo.provider == RepoProvider.GITHUB.value:
        if not githost.configured():
            return RepoCheckOut(
                repo_id=repo.id, provider=repo.provider, ok=False,
                message="No GITHUB_TOKEN configured — connect a token to push pull requests.",
            )
        try:
            info = githost.get_repo(repo.repo_full_name or "")
            return RepoCheckOut(
                repo_id=repo.id, provider=repo.provider, ok=True,
                message=f"Connected to {info['full_name']} (default branch {info['default_branch']}).",
                detail=info,
            )
        except githost.GitHubError as exc:
            return RepoCheckOut(
                repo_id=repo.id, provider=repo.provider, ok=False, message=str(exc)
            )

    if not _git_available():
        return RepoCheckOut(
            repo_id=repo.id, provider=repo.provider, ok=False,
            message="git is not installed on the server.",
        )
    if not localgit.is_repo(workspace_id):
        return RepoCheckOut(
            repo_id=repo.id, provider=repo.provider, ok=True,
            message="git is available — the sandbox repository is created on first use.",
            detail={"initialized": False},
        )
    state = localgit.status(workspace_id)
    return RepoCheckOut(
        repo_id=repo.id, provider=repo.provider, ok=True,
        message=(
            f"Local repository ready on '{state['branch']}' — "
            f"{len(state['changed_files'])} uncommitted change(s)."
        ),
        detail={"branch": state["branch"], "commit_count": state["commit_count"]},
    )


# --------------------------------------------------------------------------
# Local git state
# --------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/git/status",
    response_model=GitStatusOut,
)
def git_status(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GitStatusOut:
    """Status of the sandbox repository (creates it on first call)."""
    assert_workspace_member(db, workspace_id, user)
    if not _git_available():
        return GitStatusOut(available=False, initialized=False, clean=True)
    _init_repo(db, workspace_id, user)
    return GitStatusOut(**localgit.status(workspace_id))


@router.get(
    "/workspaces/{workspace_id}/git/diff",
    response_model=GitDiffOut,
)
def git_diff(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GitDiffOut:
    assert_workspace_member(db, workspace_id, user)
    if not _git_available():
        return GitDiffOut(diff="")
    _init_repo(db, workspace_id, user)
    text = localgit.diff(workspace_id)
    truncated = len(text) > MAX_DIFF_CHARS
    return GitDiffOut(
        branch=localgit.current_branch(workspace_id),
        diff=text[:MAX_DIFF_CHARS],
        changed_files=[ChangedFileOut(**f) for f in localgit.changed_files(workspace_id)],
        truncated=truncated,
    )


@router.get(
    "/workspaces/{workspace_id}/git/log",
    response_model=list[GitCommitOut],
)
def git_log(
    workspace_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[GitCommitOut]:
    assert_workspace_member(db, workspace_id, user)
    if not _git_available() or not localgit.is_repo(workspace_id):
        return []
    return [GitCommitOut(**c) for c in localgit.log(workspace_id, limit=limit)]


# --------------------------------------------------------------------------
# Pull-request proposals
# --------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}/pull-requests",
    response_model=list[PullRequestOut],
)
def list_pull_requests(
    workspace_id: str,
    pr_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PullRequestOut]:
    assert_workspace_member(db, workspace_id, user)
    query = db.query(PullRequestProposal).filter(
        PullRequestProposal.workspace_id == workspace_id
    )
    if pr_status:
        query = query.filter(PullRequestProposal.status == pr_status)
    rows = query.order_by(PullRequestProposal.created_at.desc()).limit(limit).all()
    return [_pr_out(pr) for pr in rows]


@router.post(
    "/workspaces/{workspace_id}/pull-requests",
    response_model=PullRequestOut,
    status_code=http_status.HTTP_201_CREATED,
)
def create_pull_request(
    workspace_id: str,
    payload: PullRequestCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PullRequestOut:
    """Snapshot the current changes as a *draft* pull-request proposal.

    Nothing is committed or pushed here — this only captures what a human is
    about to review.
    """
    assert_workspace_member(db, workspace_id, user)

    repo: RepoConnection | None = None
    if payload.repo_id:
        repo = _load_repo(db, workspace_id, payload.repo_id)

    provider = payload.provider or (repo.provider if repo else RepoProvider.LOCAL.value)
    base_branch = payload.base_branch or (repo.default_branch if repo else "main")

    if provider == RepoProvider.GITHUB.value:
        if repo is None or not repo.repo_full_name:
            raise HTTPException(
                status_code=400,
                detail="Connect a GitHub repository before proposing a pull request",
            )

    # Optional traceability guard: any referenced proposal must be approved.
    proposal_ids = list(payload.proposal_ids or [])
    if proposal_ids:
        rows = (
            db.query(CodeProposal)
            .filter(
                CodeProposal.workspace_id == workspace_id,
                CodeProposal.id.in_(proposal_ids),
            )
            .all()
        )
        if len(rows) != len(set(proposal_ids)):
            raise HTTPException(status_code=404, detail="One or more proposals were not found")
        not_approved = [p.id for p in rows if p.status != ProposalStatus.APPROVED.value]
        if not_approved:
            raise HTTPException(
                status_code=409,
                detail="Approve every referenced proposal before proposing a pull request",
            )

    if provider == RepoProvider.LOCAL.value:
        _init_repo(db, workspace_id, user)

    try:
        snap = localgit.snapshot(workspace_id)
    except localgit.GitError as exc:
        raise HTTPException(status_code=500, detail=f"git error: {exc}")

    if snap["file_count"] == 0:
        raise HTTPException(
            status_code=400,
            detail="There are no changes to ship. Approve a code change first.",
        )

    branch_name = ship.make_branch_name(payload.title, uuid.uuid4().hex)
    pr = PullRequestProposal(
        workspace_id=workspace_id,
        repo_id=repo.id if repo else None,
        provider=provider,
        title=payload.title,
        body=payload.body,
        branch_name=branch_name,
        base_branch=base_branch,
        files=snap["files"],
        skipped_files=snap["skipped"],
        diff=snap["diff"][:MAX_DIFF_CHARS],
        file_count=snap["file_count"],
        added_lines=snap["added_lines"],
        removed_lines=snap["removed_lines"],
        status=PullRequestStatus.DRAFT.value,
        meeting_id=payload.meeting_id,
        task_id=payload.task_id,
        created_by=user.id,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return _pr_out(pr)


@router.get(
    "/workspaces/{workspace_id}/pull-requests/{pr_id}",
    response_model=PullRequestOut,
)
def get_pull_request(
    workspace_id: str,
    pr_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PullRequestOut:
    assert_workspace_member(db, workspace_id, user)
    return _pr_out(_load_pr(db, workspace_id, pr_id))


@router.post(
    "/workspaces/{workspace_id}/pull-requests/{pr_id}/open",
    response_model=PullRequestDecisionOut,
)
def open_pull_request(
    workspace_id: str,
    pr_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PullRequestDecisionOut:
    """Human approval: create the real branch/commit (and PR when remote)."""
    assert_workspace_member(db, workspace_id, user)
    pr = _load_pr(db, workspace_id, pr_id)

    if pr.status not in (PullRequestStatus.DRAFT.value, PullRequestStatus.FAILED.value):
        raise HTTPException(
            status_code=409, detail=f"This proposal is already {pr.status}"
        )

    repo = db.get(RepoConnection, pr.repo_id) if pr.repo_id else None
    repo_full_name = repo.repo_full_name if repo else None

    try:
        result = ship.open_change(
            pr.provider,
            workspace_id=workspace_id,
            repo_full_name=repo_full_name,
            base_branch=pr.base_branch,
            branch=pr.branch_name,
            files=list(pr.files or []),
            title=pr.title,
            body=pr.body,
            author_name=user.name,
            author_email=user.email,
        )
    except (ship.ShipError, localgit.GitError, githost.GitHubError) as exc:
        pr.status = PullRequestStatus.FAILED.value
        pr.error = str(exc)[:1000]
        pr.decided_at = datetime.now(timezone.utc)
        pr.decided_by = user.id
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    pr.status = PullRequestStatus.OPEN.value
    pr.error = None
    pr.commit_sha = result.get("commit_sha")
    pr.external_number = result.get("external_number")
    pr.external_url = result.get("external_url")
    pr.decided_at = datetime.now(timezone.utc)
    pr.decided_by = user.id
    db.commit()
    db.refresh(pr)

    if pr.provider == RepoProvider.LOCAL.value:
        message = f"Committed to branch '{pr.branch_name}' ({pr.commit_sha[:8]})."
    else:
        message = f"Opened pull request #{pr.external_number}."
    return PullRequestDecisionOut(proposal=_pr_out(pr), message=message)


@router.post(
    "/workspaces/{workspace_id}/pull-requests/{pr_id}/merge",
    response_model=PullRequestDecisionOut,
)
def merge_pull_request(
    workspace_id: str,
    pr_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PullRequestDecisionOut:
    assert_workspace_member(db, workspace_id, user)
    pr = _load_pr(db, workspace_id, pr_id)

    if pr.status != PullRequestStatus.OPEN.value:
        raise HTTPException(
            status_code=409, detail=f"Only an open proposal can be merged (this is {pr.status})"
        )

    repo = db.get(RepoConnection, pr.repo_id) if pr.repo_id else None
    repo_full_name = repo.repo_full_name if repo else None

    try:
        ship.merge_change(
            pr.provider,
            workspace_id=workspace_id,
            repo_full_name=repo_full_name,
            base_branch=pr.base_branch,
            branch=pr.branch_name,
            external_number=pr.external_number,
        )
    except (ship.ShipError, localgit.GitError, githost.GitHubError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    pr.status = PullRequestStatus.MERGED.value
    pr.decided_at = datetime.now(timezone.utc)
    pr.decided_by = user.id
    db.commit()
    db.refresh(pr)
    return PullRequestDecisionOut(
        proposal=_pr_out(pr),
        message=f"Merged '{pr.branch_name}' into '{pr.base_branch}'.",
    )


@router.post(
    "/workspaces/{workspace_id}/pull-requests/{pr_id}/close",
    response_model=PullRequestDecisionOut,
)
def close_pull_request(
    workspace_id: str,
    pr_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PullRequestDecisionOut:
    assert_workspace_member(db, workspace_id, user)
    pr = _load_pr(db, workspace_id, pr_id)

    if pr.status in (PullRequestStatus.MERGED.value, PullRequestStatus.CLOSED.value):
        raise HTTPException(status_code=409, detail=f"This proposal is already {pr.status}")

    repo = db.get(RepoConnection, pr.repo_id) if pr.repo_id else None
    repo_full_name = repo.repo_full_name if repo else None

    try:
        ship.close_change(
            pr.provider,
            workspace_id=workspace_id,
            repo_full_name=repo_full_name,
            base_branch=pr.base_branch,
            branch=pr.branch_name,
            external_number=pr.external_number,
        )
    except (ship.ShipError, localgit.GitError, githost.GitHubError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    pr.status = PullRequestStatus.CLOSED.value
    pr.decided_at = datetime.now(timezone.utc)
    pr.decided_by = user.id
    db.commit()
    db.refresh(pr)
    return PullRequestDecisionOut(
        proposal=_pr_out(pr), message="Pull-request proposal closed."
    )
