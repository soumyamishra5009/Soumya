"""Phase 4 models: shipping the code the AI helped write.

Three pieces, all workspace-scoped and all human-gated:

* ``RepoConnection`` — where a workspace ships from: either the local git repo
  that lives inside the Dev Studio sandbox (works offline, no account) or a
  GitHub repository reached through the REST API (needs ``GITHUB_TOKEN``).
* ``CodePlan`` — the result of the Meeting→Code agent: a decision turned into
  requirements, subtasks and the files most likely to need editing.
* ``PullRequestProposal`` — a *snapshot* of the current diff, ready to become a
  real branch/commit/PR. Nothing is pushed until a human opens it.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid
from app.models.enums import PlanStatus, PullRequestStatus, RepoProvider


class RepoConnection(Base):
    """A workspace's link to a place its code can be shipped to.

    Tokens are **never** stored here — the GitHub token is read from the
    environment at call time, so a database leak cannot leak a credential.
    """

    __tablename__ = "repo_connections"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(
        String(20), default=RepoProvider.LOCAL.value, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # "owner/repo" for GitHub; the sandbox name for a local repo.
    repo_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )

    workspace = relationship("Workspace", back_populates="repo_connections")
    pull_requests = relationship(
        "PullRequestProposal", back_populates="repo", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<RepoConnection {self.provider}:{self.repo_full_name or self.name}>"


class CodePlan(Base):
    """A Meeting→Code plan: decisions turned into concrete engineering work."""

    __tablename__ = "code_plans"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    focus: Mapped[str | None] = mapped_column(Text, nullable=True)

    meeting_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    requirements: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    subtasks: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    affected_files: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    proposed_changes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    # "llm" when a model produced it, "fallback" for the offline planner.
    source: Mapped[str] = mapped_column(String(20), default="fallback", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=PlanStatus.DRAFT.value, nullable=False
    )
    proposal_ids: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )

    workspace = relationship("Workspace", back_populates="code_plans")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<CodePlan {self.title} [{self.status}]>"


class PullRequestProposal(Base):
    """A diff snapshot awaiting human approval to become a real PR.

    ``files`` holds the exact contents captured when the proposal was built, so
    opening it later pushes what the human reviewed — not whatever the sandbox
    happens to contain at that moment.
    """

    __tablename__ = "pull_request_proposals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    repo_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("repo_connections.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(20), default=RepoProvider.LOCAL.value, nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)

    # Snapshot: list of {"path", "content", "deleted", "added_lines", "removed_lines"}
    files: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    skipped_files: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    removed_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default=PullRequestStatus.DRAFT.value, nullable=False, index=True
    )
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    meeting_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decided_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    workspace = relationship("Workspace", back_populates="pull_requests")
    repo = relationship("RepoConnection", back_populates="pull_requests")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<PullRequestProposal {self.branch_name} [{self.status}]>"
