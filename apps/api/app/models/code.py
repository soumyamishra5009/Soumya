"""Dev Studio models.

A ``CodeProposal`` is an AI-suggested change to a single file in a workspace's
sandbox tree. It is deliberately *not* applied until a human approves it
(human-in-the-loop): the AI never commits or deploys on its own.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid
from app.models.enums import ProposalStatus


class CodeProposal(Base):
    __tablename__ = "code_proposals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Sandbox-relative path, e.g. "src/app.py" (never absolute, never escapes).
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)

    original_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    # "llm" when a model produced it, "fallback" for the offline scaffold.
    source: Mapped[str] = mapped_column(String(20), default="fallback", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ProposalStatus.PENDING.value, nullable=False, index=True
    )

    # sha256 of original_content at proposal time. Approving a proposal whose
    # file has since changed is refused, so a human cannot be surprised by a
    # stale edit silently overwriting newer work.
    base_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Rough change size, computed once so listings do not need a diff library.
    added_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    removed_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Optional traceability back to the meeting/task the change came from.
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

    workspace = relationship("Workspace", back_populates="code_proposals")

    def __repr__(self) -> str:
        return f"<CodeProposal {self.file_path} [{self.status}]>"
