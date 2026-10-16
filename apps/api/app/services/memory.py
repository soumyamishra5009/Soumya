"""Project Memory: a workspace-scoped retrieval index (Phase 5 RAG).

Everything a workspace knows — meeting summaries, decisions, tasks and the code
in its sandbox — is chunked, embedded and stored so a single query can surface
"what did we decide about X?" across all of it.

Embeddings follow SyncForge's usual degradation ladder:

* **llm** — Ollama's ``nomic-embed-text`` when it is reachable;
* **fallback** — a deterministic *hashing* embedding (the hashing trick over word
  unigrams and character trigrams, L2-normalised). It needs no model, no network
  and no API key, and it makes lexical overlap translate directly into cosine
  similarity, so search stays genuinely useful offline.

Vectors are plain JSON lists, so the SQLite dev database needs no extensions. In
production the same rows can be stored as ``vector`` columns in Postgres with
pgvector without changing this module's interface.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Any, Iterable, Sequence

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import MemorySourceType
from app.models.meeting import Meeting
from app.models.memory import MemoryChunk
from app.models.task import Task
from app.services import devstudio

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")
_CAMEL_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")

_TYPES = {t.value for t in MemorySourceType}


class MemoryServiceError(RuntimeError):
    """Raised for invalid memory operations (bad query, empty workspace, ...)."""


# --------------------------------------------------------------------------
# Tokenising and the offline embedder
# --------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, with camelCase/``snake_case`` identifiers split."""
    out: list[str] = []
    for raw in _WORD_RE.findall(text or ""):
        for part in re.split(r"[_\W]+", raw):
            if not part:
                continue
            for chunk in _CAMEL_RE.findall(part) or [part]:
                token = chunk.lower()
                if len(token) >= 2:
                    out.append(token)
    return out


def _bucket(token: str, dim: int) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % dim, (1.0 if (value >> 63) & 1 else -1.0)


def hash_embed(text: str, dim: int | None = None) -> list[float]:
    """Deterministic hashing embedding (no model, no network)."""
    dimension = dim or settings.MEMORY_EMBED_DIM
    vec = [0.0] * dimension
    tokens = tokenize(text)
    if not tokens:
        return vec

    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1

    for token, count in counts.items():
        idx, sign = _bucket(token, dimension)
        vec[idx] += sign * (1.0 + math.log(count))
        # Character trigrams give some resilience to morphology/typos.
        if len(token) >= 5:
            for i in range(len(token) - 2):
                tri_idx, tri_sign = _bucket("#" + token[i : i + 3], dimension)
                vec[tri_idx] += tri_sign * 0.35

    norm = math.sqrt(sum(v * v for v in vec))
    if norm:
        vec = [v / norm for v in vec]
    return [round(v, 5) for v in vec]


def _embed_batch(texts: Sequence[str]) -> tuple[list[list[float]], str]:
    """Embed one batch, preferring the model and falling back to hashing."""
    try:
        from app.services.llm import embed

        vectors = embed(list(texts))
        if vectors and all(isinstance(v, list) and v for v in vectors):
            return [[float(x) for x in v] for v in vectors], "llm"
    except Exception as exc:  # noqa: BLE001 - any provider failure means fallback
        logger.info("embedding model unavailable (%s); using offline hashing", exc)
    return [hash_embed(t) for t in texts], "fallback"


def embed_texts(texts: Sequence[str]) -> tuple[list[list[float]], str]:
    """Embed many texts with one consistent backend. Returns ``(vectors, source)``."""
    if not texts:
        return [], "fallback"

    batch = 32
    source: str | None = None
    first = list(texts[:batch])
    vectors, source = _embed_batch(first)
    out = list(vectors)

    for start in range(batch, len(texts), batch):
        chunk = list(texts[start : start + batch])
        if source == "llm":
            try:
                from app.services.llm import embed

                out.extend([[float(x) for x in v] for v in embed(chunk)])
                continue
            except Exception:  # noqa: BLE001 - degrade for the rest of the run
                source = "fallback"
        out.extend([hash_embed(t) for t in chunk])
    return out, source


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity with a zero-vector guard."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """Split text into overlapping chunks, preferring newline boundaries."""
    body = (text or "").strip()
    if not body:
        return []
    limit = size or settings.MEMORY_CHUNK_CHARS
    lap = overlap if overlap is not None else settings.MEMORY_CHUNK_OVERLAP
    if len(body) <= limit:
        return [body]

    chunks: list[str] = []
    start = 0
    while start < len(body):
        end = min(start + limit, len(body))
        if end < len(body):
            newline = body.rfind("\n", start + int(limit * 0.6), end)
            if newline != -1:
                end = newline + 1
        piece = body[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(body):
            break
        start = max(end - lap, start + 1)
    return chunks


def _digest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Source collection
# --------------------------------------------------------------------------


def _meeting_text(meeting: Meeting) -> str:
    parts: list[str] = []
    if meeting.title:
        parts.append(meeting.title)
    if meeting.summary:
        parts.append(meeting.summary)
    if meeting.key_points:
        parts.append("Key points:\n" + "\n".join(f"- {p}" for p in meeting.key_points))
    if meeting.next_steps:
        parts.append("Next steps:\n" + "\n".join(f"- {p}" for p in meeting.next_steps))
    return "\n\n".join(str(p) for p in parts)


def collect_sources(
    db: Session, workspace_id: str, *, include_code: bool = True
) -> list[dict[str, Any]]:
    """Everything that can be indexed, as ``{type, id, title, text, meta}`` records."""
    records: list[dict[str, Any]] = []

    meetings = (
        db.query(Meeting)
        .filter(Meeting.workspace_id == workspace_id)
        .order_by(Meeting.created_at.desc())
        .all()
    )
    for meeting in meetings:
        text = _meeting_text(meeting)
        if text.strip():
            records.append({
                "type": MemorySourceType.MEETING.value,
                "id": meeting.id,
                "title": meeting.title or "Meeting",
                "text": text,
                "meta": {"meeting_id": meeting.id},
            })
        for decision in meeting.decisions:
            body = "\n".join(
                str(x) for x in (decision.title, decision.description, decision.rationale) if x
            )
            if body.strip():
                records.append({
                    "type": MemorySourceType.DECISION.value,
                    "id": decision.id,
                    "title": decision.title or "Decision",
                    "text": body,
                    "meta": {"meeting_id": meeting.id, "impact": decision.impact},
                })

    tasks = db.query(Task).filter(Task.workspace_id == workspace_id).all()
    for task in tasks:
        body = "\n".join(str(x) for x in (task.title, task.description) if x)
        if body.strip():
            records.append({
                "type": MemorySourceType.TASK.value,
                "id": task.id,
                "title": task.title or "Task",
                "text": body,
                "meta": {"status": task.status, "priority": task.priority},
            })

    if include_code:
        root = devstudio.workspace_root(workspace_id)
        if root.exists():
            tree = devstudio.list_tree(workspace_id)
            paths = devstudio.flatten_paths(tree, settings.MEMORY_INDEX_MAX_FILES)
            for rel in paths:
                if not devstudio.is_editable(rel):
                    continue
                try:
                    path, _ = devstudio.resolve_path(workspace_id, rel)
                except devstudio.SandboxError:
                    continue
                if not path.is_file() or path.stat().st_size > devstudio.max_file_bytes():
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if not content.strip():
                    continue
                records.append({
                    "type": MemorySourceType.FILE.value,
                    "id": rel,
                    "title": rel,
                    "text": content,
                    "meta": {"path": rel, "language": devstudio.language_for(rel)},
                })

    return records


# --------------------------------------------------------------------------
# Indexing
# --------------------------------------------------------------------------


def _existing(db: Session, workspace_id: str) -> dict[tuple[str, str, int], MemoryChunk]:
    rows = db.query(MemoryChunk).filter(MemoryChunk.workspace_id == workspace_id).all()
    return {(r.source_type, r.source_id, r.chunk_index): r for r in rows}


def index_workspace(
    db: Session,
    workspace_id: str,
    *,
    include_code: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """(Re)build the workspace index. Returns counts and the embedding backend."""
    records = collect_sources(db, workspace_id, include_code=include_code)
    existing = _existing(db, workspace_id)

    # Decide the embedding backend once, using a representative sample.
    sample = [r["text"][:400] for r in records[:1]] or ["syncforge"]
    _, embed_source = _embed_batch(sample)
    target_dim = settings.MEMORY_EMBED_DIM if embed_source == "fallback" else None

    indexed = skipped = 0
    by_type: dict[str, int] = {}
    seen: dict[str, set[str]] = {}
    counts: dict[tuple[str, str], int] = {}
    pending: list[tuple[MemoryChunk, str]] = []
    created = 0

    for record in records:
        source_type = record["type"]
        source_id = record["id"]
        seen.setdefault(source_type, set()).add(source_id)

        chunks = chunk_text(record["text"])
        counts[(source_type, source_id)] = len(chunks)
        for position, piece in enumerate(chunks):
            key = (source_type, source_id, position)
            digest = _digest(piece)
            current = existing.get(key)
            if (
                current is not None
                and not force
                and current.content_hash == digest
                and current.embedding
                and (embed_source == "llm" or current.dim == target_dim)
                and current.embed_source == embed_source
            ):
                skipped += 1
                by_type[source_type] = by_type.get(source_type, 0) + 1
                continue

            row = current or MemoryChunk(workspace_id=workspace_id, source_type=source_type,
                                         source_id=source_id, chunk_index=position)
            row.title = record["title"][:500]
            row.text = piece
            row.content_hash = digest
            row.meta = record["meta"]
            if current is None:
                db.add(row)
                created += 1
            pending.append((row, piece))
            indexed += 1
            by_type[source_type] = by_type.get(source_type, 0) + 1

    # Embed everything that changed in one batch.
    if pending:
        vectors, _ = embed_texts([piece for _, piece in pending])
        for (row, _), vector in zip(pending, vectors):
            row.embedding = vector
            row.dim = len(vector)
            row.embed_source = embed_source

    # Drop stale chunks (source deleted, or now shorter).
    removed = 0
    for key, row in existing.items():
        source_type, source_id, position = key
        if source_type not in seen or source_id not in seen[source_type]:
            db.delete(row)
            removed += 1
        elif position >= counts.get((source_type, source_id), 0):
            db.delete(row)
            removed += 1

    db.commit()

    total = db.query(MemoryChunk).filter(MemoryChunk.workspace_id == workspace_id).count()
    dim = target_dim or settings.MEMORY_EMBED_DIM
    if pending and pending[0][0].embedding:
        dim = len(pending[0][0].embedding)
    else:
        sample_row = (
            db.query(MemoryChunk)
            .filter(MemoryChunk.workspace_id == workspace_id, MemoryChunk.dim > 0)
            .first()
        )
        if sample_row is not None:
            dim = sample_row.dim

    return {
        "indexed": indexed,
        "created": created,
        "skipped": skipped,
        "removed": removed,
        "chunks": total,
        "by_type": by_type,
        "source": embed_source,
        "dim": dim,
    }


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------


def _snippet(text: str, limit: int = 360) -> str:
    body = " ".join((text or "").split())
    if len(body) <= limit:
        return body
    return body[:limit].rsplit(" ", 1)[0] + " …"


def search(
    db: Session,
    workspace_id: str,
    query: str,
    *,
    k: int | None = None,
    types: Iterable[str] | None = None,
    min_score: float | None = None,
) -> dict[str, Any]:
    """Rank indexed chunks against a query. Returns scored results + metadata."""
    text = (query or "").strip()
    if not text:
        raise MemoryServiceError("A search query is required")

    top_k = max(1, min(int(k or settings.MEMORY_TOP_K), 25))
    wanted = [t for t in (types or []) if t in _TYPES]

    row_query = db.query(MemoryChunk).filter(MemoryChunk.workspace_id == workspace_id)
    if wanted:
        row_query = row_query.filter(MemoryChunk.source_type.in_(wanted))
    rows = row_query.limit(settings.MEMORY_MAX_CHUNKS).all()

    vectors, source = embed_texts([text])
    query_vector = vectors[0]
    query_dim = len(query_vector)

    threshold = settings.MEMORY_MIN_SCORE if min_score is None else float(min_score)

    scored: list[tuple[float, MemoryChunk]] = []
    for row in rows:
        if not row.embedding or row.dim != query_dim:
            continue
        score = cosine(query_vector, row.embedding)
        if score >= threshold:
            scored.append((score, row))

    scored.sort(key=lambda pair: (-pair[0], pair[1].source_id))

    results = [
        {
            "chunk_id": row.id,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "title": row.title,
            "score": round(score, 4),
            "snippet": _snippet(row.text),
            "meta": row.meta or {},
        }
        for score, row in scored[:top_k]
    ]

    return {
        "query": text,
        "count": len(results),
        "results": results,
        "source": source,
        "dim": query_dim,
        "indexed": len(rows),
        "min_score": threshold,
    }


# --------------------------------------------------------------------------
# Stats / maintenance
# --------------------------------------------------------------------------


def stats(db: Session, workspace_id: str) -> dict[str, Any]:
    rows = db.query(MemoryChunk).filter(MemoryChunk.workspace_id == workspace_id).all()
    by_type: dict[str, int] = {}
    for row in rows:
        by_type[row.source_type] = by_type.get(row.source_type, 0) + 1
    return {
        "chunks": len(rows),
        "by_type": by_type,
        "dims": sorted({row.dim for row in rows if row.dim}),
        "embed_sources": sorted({row.embed_source for row in rows}),
        "max_chunks": settings.MEMORY_MAX_CHUNKS,
    }


def clear(db: Session, workspace_id: str, source_type: str | None = None) -> int:
    query = db.query(MemoryChunk).filter(MemoryChunk.workspace_id == workspace_id)
    if source_type:
        if source_type not in _TYPES:
            raise MemoryServiceError(f"Unknown source type {source_type!r}")
        query = query.filter(MemoryChunk.source_type == source_type)
    removed = query.delete(synchronize_session=False)
    db.commit()
    return int(removed or 0)
