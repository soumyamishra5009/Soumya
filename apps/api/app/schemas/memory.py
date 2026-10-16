"""Phase 5 schemas: Project Memory (workspace RAG)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryIndexRequest(BaseModel):
    include_code: bool = True
    force: bool = False


class MemoryIndexOut(BaseModel):
    indexed: int = 0
    created: int = 0
    skipped: int = 0
    removed: int = 0
    chunks: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    source: str = "fallback"
    dim: int = 0
    message: str = ""


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    k: int | None = Field(default=None, ge=1, le=25)
    types: list[str] = Field(default_factory=list)


class MemoryHit(BaseModel):
    chunk_id: str
    source_type: str
    source_id: str
    title: str = ""
    score: float = 0.0
    snippet: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class MemorySearchOut(BaseModel):
    query: str
    count: int = 0
    results: list[MemoryHit] = Field(default_factory=list)
    source: str = "fallback"
    dim: int = 0
    indexed: int = 0
    min_score: float = 0.0
    message: str = ""


class MemoryStatsOut(BaseModel):
    chunks: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    dims: list[int] = Field(default_factory=list)
    embed_sources: list[str] = Field(default_factory=list)
    max_chunks: int = 0


class MemoryChunkOut(BaseModel):
    id: str
    workspace_id: str
    source_type: str
    source_id: str
    title: str = ""
    chunk_index: int = 0
    text: str = ""
    dim: int = 0
    embed_source: str = "fallback"
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryClearOut(BaseModel):
    removed: int = 0
    message: str = ""
