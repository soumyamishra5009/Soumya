"""Phase 5 model: Project Memory — a workspace-scoped retrieval index.

Every chunk is one searchable passage (a meeting summary, a decision, a task, a
file slice) plus its embedding. Embeddings are stored as JSON so the default
SQLite dev database needs no extensions; a real deployment can swap the storage
for pgvector without changing the API surface.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, generate_uuid
from app.models.enums import MemorySourceType


class MemoryChunk(Base):
    __tablename__ = "memory_chunks"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source_type", "source_id", "chunk_index",
                         name="uq_memory_chunks_source"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source_type: Mapped[str] = mapped_column(
        String(20), default=MemorySourceType.NOTE.value, nullable=False, index=True
    )
    # Id of the originating row (meeting/decision/task) or the file path.
    source_id: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256 of the chunk text: unchanged sources are skipped on re-index.
    content_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    # Embedding vector as a JSON list of floats, plus its dimension and which
    # embedder produced it ("llm" for a model, "fallback" for the offline one).
    embedding: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    dim: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embed_source: Mapped[str] = mapped_column(String(20), default="fallback", nullable=False)

    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )

    workspace = relationship("Workspace", back_populates="memory_chunks")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<MemoryChunk {self.source_type}:{self.source_id}#{self.chunk_index}>"
