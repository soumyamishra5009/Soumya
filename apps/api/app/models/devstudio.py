"""Dev Studio file model (DB-backed sandbox).

Used when ``DEVSTUDIO_BACKEND=db`` — the tree lives as rows in Postgres instead
of on a local filesystem, so the studio works on serverless hosts (Vercel,
Netlify) that have no writable persistent disk.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class WorkspaceFile(Base):
    __tablename__ = "workspace_files"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Sandbox-relative POSIX path, e.g. "src/calculator.py". Never absolute.
    path: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    is_dir: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # File content (None for directories). Capped by DEVSTUDIO_MAX_FILE_KB.
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        kind = "dir" if self.is_dir else "file"
        return f"<WorkspaceFile {self.workspace_id}/{self.path} [{kind}]>"
