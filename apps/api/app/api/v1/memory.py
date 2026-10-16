"""Phase 5 endpoints: Project Memory (workspace retrieval index).

Indexes everything a workspace knows — meetings, decisions, tasks and sandbox
code — and answers natural-language queries across all of it. Works offline with
deterministic embeddings; uses a real embedding model automatically when one is
reachable.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import assert_workspace_member, get_current_user
from app.models.memory import MemoryChunk
from app.models.user import User
from app.schemas.memory import (
    MemoryChunkOut,
    MemoryClearOut,
    MemoryIndexOut,
    MemoryIndexRequest,
    MemorySearchOut,
    MemorySearchRequest,
    MemoryStatsOut,
)
from app.services import memory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["memory"])


@router.post(
    "/workspaces/{workspace_id}/memory/index",
    response_model=MemoryIndexOut,
)
def index_workspace(
    workspace_id: str,
    payload: MemoryIndexRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryIndexOut:
    """(Re)index the workspace. Unchanged chunks are skipped unless ``force``."""
    assert_workspace_member(db, workspace_id, user)
    result = memory.index_workspace(
        db, workspace_id, include_code=payload.include_code, force=payload.force
    )
    indexed = result["indexed"]
    skipped = result["skipped"]
    source = result["source"]
    notice = " (offline embeddings)" if source == "fallback" else " (embedding model)"
    message = (
        f"Indexed {indexed} new/updated chunk(s), skipped {skipped} unchanged, "
        f"removed {result['removed']} stale — {result['chunks']} total{notice}."
    )
    return MemoryIndexOut(**result, message=message)


@router.post(
    "/workspaces/{workspace_id}/memory/search",
    response_model=MemorySearchOut,
)
def search_memory(
    workspace_id: str,
    payload: MemorySearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemorySearchOut:
    """Semantic-ish search across the workspace's indexed memory."""
    assert_workspace_member(db, workspace_id, user)
    try:
        result = memory.search(
            db, workspace_id, payload.query, k=payload.k, types=payload.types
        )
    except memory.MemoryServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    message = ""
    if result["indexed"] == 0:
        message = "The workspace has no indexed memory yet — run Index first."
    elif result["count"] == 0:
        message = "No chunk was similar enough to the query. Try different wording."
    return MemorySearchOut(**result, message=message)


@router.get(
    "/workspaces/{workspace_id}/memory/stats",
    response_model=MemoryStatsOut,
)
def memory_stats(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryStatsOut:
    assert_workspace_member(db, workspace_id, user)
    return MemoryStatsOut(**memory.stats(db, workspace_id))


@router.get(
    "/workspaces/{workspace_id}/memory/chunks",
    response_model=list[MemoryChunkOut],
)
def list_chunks(
    workspace_id: str,
    source_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MemoryChunk]:
    assert_workspace_member(db, workspace_id, user)
    query = db.query(MemoryChunk).filter(MemoryChunk.workspace_id == workspace_id)
    if source_type:
        query = query.filter(MemoryChunk.source_type == source_type)
    return (
        query.order_by(MemoryChunk.source_type, MemoryChunk.source_id, MemoryChunk.chunk_index)
        .limit(limit)
        .all()
    )


@router.delete(
    "/workspaces/{workspace_id}/memory/chunks/{chunk_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
def delete_chunk(
    workspace_id: str,
    chunk_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    assert_workspace_member(db, workspace_id, user)
    chunk = db.get(MemoryChunk, chunk_id)
    if chunk is None or chunk.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Memory chunk not found")
    db.delete(chunk)
    db.commit()


@router.delete(
    "/workspaces/{workspace_id}/memory",
    response_model=MemoryClearOut,
)
def clear_memory(
    workspace_id: str,
    source_type: str | None = Query(default=None, alias="type"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryClearOut:
    assert_workspace_member(db, workspace_id, user)
    try:
        removed = memory.clear(db, workspace_id, source_type)
    except memory.MemoryServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return MemoryClearOut(
        removed=removed,
        message=f"Removed {removed} memory chunk(s). Re-index to rebuild.",
    )
