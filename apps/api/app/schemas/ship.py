"""Phase 4 schemas: repositories, git, pull-request proposals and code plans."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Repositories
# --------------------------------------------------------------------------


class RepoConnectionCreate(BaseModel):
    provider: Literal["local", "github"] = "local"
    name: str | None = Field(default=None, max_length=255)
    repo_full_name: str | None = Field(default=None, max_length=255)
    default_branch: str = Field(default="main", max_length=255)


class RepoConnectionOut(BaseModel):
    id: str
    workspace_id: str
    provider: str
    name: str
    repo_full_name: str | None = None
    default_branch: str
    is_active: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RepoCheckOut(BaseModel):
    repo_id: str
    provider: str
    ok: bool
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Git (local provider)
# --------------------------------------------------------------------------


class ChangedFileOut(BaseModel):
    path: str
    status: str = "modified"


class GitStatusOut(BaseModel):
    available: bool = True
    initialized: bool = False
    branch: str | None = None
    branches: list[str] = Field(default_factory=list)
    clean: bool = True
    changed_files: list[ChangedFileOut] = Field(default_factory=list)
    commit_count: int = 0


class GitCommitOut(BaseModel):
    sha: str
    author_name: str = ""
    author_email: str = ""
    date: str = ""
    message: str = ""


class GitDiffOut(BaseModel):
    branch: str | None = None
    diff: str = ""
    changed_files: list[ChangedFileOut] = Field(default_factory=list)
    truncated: bool = False


# --------------------------------------------------------------------------
# Pull-request proposals
# --------------------------------------------------------------------------


class PullRequestCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str | None = Field(default=None, max_length=20000)
    provider: Literal["local", "github"] | None = None
    repo_id: str | None = None
    base_branch: str | None = Field(default=None, max_length=255)
    meeting_id: str | None = None
    task_id: str | None = None
    # Optional: only ship the change these proposals produced (for traceability).
    proposal_ids: list[str] = Field(default_factory=list)


class PullRequestFileOut(BaseModel):
    path: str
    status: str = "modified"
    deleted: bool = False
    added_lines: int = 0
    removed_lines: int = 0


class PullRequestOut(BaseModel):
    id: str
    workspace_id: str
    repo_id: str | None = None
    provider: str
    title: str
    body: str | None = None
    branch_name: str
    base_branch: str
    status: str
    changed_files: list[PullRequestFileOut] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)
    diff: str | None = None
    file_count: int = 0
    added_lines: int = 0
    removed_lines: int = 0
    commit_sha: str | None = None
    external_number: int | None = None
    external_url: str | None = None
    error: str | None = None
    meeting_id: str | None = None
    task_id: str | None = None
    created_by: str | None = None
    decided_by: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class PullRequestDecisionOut(BaseModel):
    proposal: PullRequestOut
    message: str = ""


# --------------------------------------------------------------------------
# Meeting→Code plans
# --------------------------------------------------------------------------


class PlanCreateRequest(BaseModel):
    meeting_id: str | None = None
    decision_id: str | None = None
    task_id: str | None = None
    focus: str | None = Field(default=None, max_length=2000)


class PlanSubtask(BaseModel):
    title: str
    kind: str = "code"
    files: list[str] = Field(default_factory=list)


class PlanFile(BaseModel):
    path: str
    reason: str = ""
    score: int = 0


class PlanChange(BaseModel):
    path: str
    instruction: str


class CodePlanOut(BaseModel):
    id: str
    workspace_id: str
    title: str
    summary: str | None = None
    focus: str | None = None
    meeting_id: str | None = None
    decision_id: str | None = None
    task_id: str | None = None
    requirements: list[str] = Field(default_factory=list)
    subtasks: list[PlanSubtask] = Field(default_factory=list)
    affected_files: list[PlanFile] = Field(default_factory=list)
    proposed_changes: list[PlanChange] = Field(default_factory=list)
    source: str = "fallback"
    status: str = "draft"
    proposal_ids: list[str] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PlanApplyOut(BaseModel):
    plan: CodePlanOut
    created: int = 0
    proposal_ids: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    message: str = ""
