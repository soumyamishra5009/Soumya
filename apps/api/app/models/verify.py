"""Phase 5 model: sandboxed test runs (the "verification" step).

A ``TestRun`` is a record of one execution of a workspace's tests inside its Dev
Studio sandbox. It is the evidence a human looks at before shipping, and it is
never able to touch anything outside the sandbox.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid
from app.models.enums import TestRunStatus


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Requested selector: "auto" | "python" | "node".
    kind: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    # Which executor actually ran it: pytest | builtin | node | judge0.
    runner: Mapped[str] = mapped_column(String(20), default="builtin", nullable=False)
    # Human-readable command line (never executed through a shell).
    command: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    # Sandbox-relative target the run was scoped to, if any.
    target: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=TestRunStatus.ERROR.value, nullable=False, index=True
    )
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    output: Mapped[str] = mapped_column(Text, default="", nullable=False)
    output_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # "local" (subprocess) or "judge0" (remote sandbox).
    source: Mapped[str] = mapped_column(String(20), default="local", nullable=False)

    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )

    workspace = relationship("Workspace", back_populates="test_runs")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<TestRun {self.runner} [{self.status}] {self.passed}/{self.failed}>"
