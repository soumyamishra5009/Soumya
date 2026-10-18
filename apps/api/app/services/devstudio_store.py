"""Dev Studio storage backends.

Two implementations behind one interface:

* ``DiskStore`` — the original local-filesystem sandbox (dev / container hosts).
* ``DbStore``   — the tree lives as ``WorkspaceFile`` rows in the database, so
  the studio works on serverless hosts (Vercel, Netlify) that have no writable
  persistent filesystem.

The active backend is chosen with ``DEVSTUDIO_BACKEND`` (default ``"disk"``).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.devstudio import WorkspaceFile

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Path helpers (kept local so this module has no circular import with devstudio)
# --------------------------------------------------------------------------


def _safe_id(workspace_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", workspace_id or "")
    if not safe_id:
        raise ValueError("Invalid workspace id")
    return safe_id


def _normalize_rel(rel_path: str) -> str:
    raw = (rel_path or "").strip().replace("\\", "/")
    if not raw or raw in (".", "/", "./"):
        raise ValueError("A file path is required")
    if "\x00" in raw:
        raise ValueError("Invalid path")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or raw.startswith("~"):
        raise ValueError("Absolute paths are not allowed")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("Path traversal is not allowed")
    if any(p == ".git" for p in parts):
        raise ValueError("The .git directory is managed automatically")
    if not parts:
        raise ValueError("A file path is required")
    return "/".join(parts)


def _content_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _max_file_bytes() -> int:
    return settings.DEVSTUDIO_MAX_FILE_KB * 1024


def _language_for(rel_path: str) -> str:
    from app.services.devstudio import language_for

    return language_for(rel_path)


def _is_editable(rel_path: str) -> bool:
    from app.services.devstudio import is_editable

    return is_editable(rel_path)


# --------------------------------------------------------------------------
# Disk backend (the original local-filesystem sandbox)
# --------------------------------------------------------------------------


class DiskStore:
    """Local-filesystem sandbox rooted at ``settings.DEVSTUDIO_ROOT/<ws>``.

    The disk implementation lives *here* rather than in
    ``app.services.devstudio`` so that module's public functions can route
    through ``_store(db)`` without delegating back into this class (that cycle
    recursed infinitely). Pure helpers (path normalisation, tree builders,
    ``SAMPLE_FILES``) are imported lazily from ``devstudio`` to avoid a
    circular import.
    """

    name = "disk"

    def list_tree(self, workspace_id: str) -> dict[str, Any]:
        from app.services.devstudio import _build_dir, workspace_root

        root = workspace_root(workspace_id)
        counter = [0]
        truncated = [False]
        if not root.exists():
            return {
                "name": "workspace",
                "path": "",
                "type": "dir",
                "children": [],
                "empty": True,
                "count": 0,
                "truncated": False,
            }
        node = _build_dir(root, "", 0, counter, truncated)
        node["name"] = "workspace"
        node["path"] = ""
        node["count"] = counter[0]
        node["empty"] = counter[0] == 0
        node["truncated"] = truncated[0]
        return node

    def read_file(self, workspace_id: str, rel_path: str) -> dict[str, Any]:
        from app.services.devstudio import (
            SandboxError,
            _mtime,
            content_hash,
            is_editable,
            language_for,
            max_file_bytes,
            resolve_path,
        )

        path, rel = resolve_path(workspace_id, rel_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"{rel} not found")
        if not is_editable(rel):
            raise SandboxError(f"{rel} is not an editable text file")
        size = path.stat().st_size
        if size > max_file_bytes():
            raise SandboxError(
                f"{rel} is {size // 1024} KB, above the "
                f"{settings.DEVSTUDIO_MAX_FILE_KB} KB editor limit"
            )
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SandboxError(f"{rel} is not valid UTF-8 text") from exc
        return {
            "path": rel,
            "name": path.name,
            "language": language_for(rel),
            "content": text,
            "size": size,
            "editable": True,
            "hash": content_hash(text),
            "updated_at": _mtime(path),
        }

    def write_file(self, workspace_id: str, rel_path: str, content: str) -> dict[str, Any]:
        from app.services.devstudio import (
            SandboxError,
            _mtime,
            content_hash,
            is_editable,
            language_for,
            max_file_bytes,
            resolve_path,
        )

        path, rel = resolve_path(workspace_id, rel_path)
        if not is_editable(rel):
            raise SandboxError(f"{rel} is not an editable text file")
        payload = content if isinstance(content, str) else ""
        encoded = payload.encode("utf-8")
        if len(encoded) > max_file_bytes():
            raise SandboxError(
                f"Content is {len(encoded) // 1024} KB, above the "
                f"{settings.DEVSTUDIO_MAX_FILE_KB} KB limit"
            )
        if path.exists() and path.is_dir():
            raise SandboxError(f"{rel} is a directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        return {
            "path": rel,
            "name": path.name,
            "language": language_for(rel),
            "content": payload,
            "size": len(encoded),
            "editable": True,
            "hash": content_hash(payload),
            "updated_at": _mtime(path),
        }

    def create_file(self, workspace_id: str, rel_path: str, content: str = "") -> dict[str, Any]:
        from app.services.devstudio import SandboxError, resolve_path

        path, rel = resolve_path(workspace_id, rel_path)
        if path.exists():
            raise SandboxError(f"{rel} already exists")
        return self.write_file(workspace_id, rel, content)

    def create_dir(self, workspace_id: str, rel_path: str) -> dict[str, Any]:
        from app.services.devstudio import SandboxError, resolve_path

        path, rel = resolve_path(workspace_id, rel_path)
        if path.exists() and path.is_file():
            raise SandboxError(f"{rel} is a file")
        path.mkdir(parents=True, exist_ok=True)
        return {"path": rel, "name": path.name, "type": "dir"}

    def delete_entry(self, workspace_id: str, rel_path: str) -> dict[str, Any]:
        from app.services.devstudio import SandboxError, resolve_path, workspace_root

        path, rel = resolve_path(workspace_id, rel_path)
        root = workspace_root(workspace_id).resolve()
        if path.resolve() == root:
            raise SandboxError("Cannot delete the workspace root")
        if not path.exists():
            raise FileNotFoundError(f"{rel} not found")
        if path.is_dir():
            import shutil

            shutil.rmtree(path)
            return {"path": rel, "type": "dir", "deleted": True}
        path.unlink()
        return {"path": rel, "type": "file", "deleted": True}

    def seed_sample(self, workspace_id: str) -> list[str]:
        from app.services.devstudio import SAMPLE_FILES, resolve_path

        created: list[str] = []
        for rel, content in SAMPLE_FILES.items():
            path, _ = resolve_path(workspace_id, rel)
            if path.exists():
                continue
            self.write_file(workspace_id, rel, content)
            created.append(rel)
        return created

    def read_content(self, workspace_id: str, rel_path: str) -> str | None:
        try:
            return self.read_file(workspace_id, rel_path)["content"]
        except Exception:
            return None

    def file_exists(self, workspace_id: str, rel_path: str) -> bool:
        from app.services.devstudio import resolve_path

        try:
            path, _ = resolve_path(workspace_id, rel_path)
            return path.exists()
        except Exception:
            return False

    def get_all_files(self, workspace_id: str) -> list[dict[str, Any]]:
        from app.services.devstudio import is_editable, workspace_root

        root = workspace_root(workspace_id)
        out: list[dict[str, Any]] = []
        if not root.exists():
            return out
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if not is_editable(rel):
                continue
            try:
                if path.stat().st_size > 200_000:  # keep Piston payloads small
                    continue
                out.append({"path": rel, "content": path.read_text(encoding="utf-8")})
            except (OSError, UnicodeDecodeError):
                continue
        return out


# --------------------------------------------------------------------------
# Database backend
# --------------------------------------------------------------------------


class DbStore:
    """DB-backed sandbox — the tree is ``WorkspaceFile`` rows."""

    name = "db"

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- helpers ---------------------------------------------------------

    def _rows(self, workspace_id: str) -> list[WorkspaceFile]:
        stmt = (
            select(WorkspaceFile)
            .where(WorkspaceFile.workspace_id == _safe_id(workspace_id))
            .order_by(WorkspaceFile.path)
        )
        return list(self.db.scalars(stmt))

    def _one(self, workspace_id: str, rel: str) -> WorkspaceFile | None:
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.workspace_id == _safe_id(workspace_id),
            WorkspaceFile.path == rel,
        )
        return self.db.scalar(stmt)

    def _ensure_parent_dirs(self, workspace_id: str, rel: str) -> None:
        """Insert intermediate directory rows so the tree is complete."""
        parts = rel.split("/")
        for i in range(1, len(parts)):
            parent_rel = "/".join(parts[:i])
            existing = self._one(workspace_id, parent_rel)
            if existing is None:
                self.db.add(WorkspaceFile(
                    workspace_id=workspace_id,
                    path=parent_rel,
                    is_dir=True,
                    content=None,
                    size=0,
                ))

    def _make_node(self, wf: WorkspaceFile, rel: str) -> dict[str, Any]:
        if wf.is_dir:
            return {
                "name": rel.rsplit("/", 1)[-1] if "/" in rel else rel,
                "path": rel,
                "type": "dir",
                "children": [],
            }
        return {
            "name": rel.rsplit("/", 1)[-1] if "/" in rel else rel,
            "path": rel,
            "type": "file",
            "size": wf.size or 0,
            "language": _language_for(rel),
            "editable": _is_editable(rel),
        }

    # -- public interface ------------------------------------------------

    def list_tree(self, workspace_id: str) -> dict[str, Any]:
        rows = self._rows(workspace_id)
        if not rows:
            return {
                "name": "workspace",
                "path": "",
                "type": "dir",
                "children": [],
                "empty": True,
                "count": 0,
                "truncated": False,
            }

        # Build a flat map path -> node, then link children.
        nodes: dict[str, dict[str, Any]] = {}
        dirs: dict[str, dict[str, Any]] = {}
        for wf in rows:
            node = self._make_node(wf, wf.path)
            nodes[wf.path] = node
            if wf.is_dir:
                dirs[wf.path] = node

        root: dict[str, Any] = {
            "name": "workspace",
            "path": "",
            "type": "dir",
            "children": [],
        }

        # Link each node under its parent.
        for path, node in nodes.items():
            if "/" in path:
                parent_rel = path.rsplit("/", 1)[0]
                parent = dirs.get(parent_rel)
                if parent is not None:
                    parent["children"].append(node)
                    continue
            # Top-level entry (or parent missing — shouldn't happen).
            root["children"].append(node)

        # Sort children: dirs first, then by name.
        def sort_children(n: dict[str, Any]) -> None:
            n["children"].sort(key=lambda c: (c["type"] != "dir", c["name"].lower()))
            for c in n["children"]:
                if c["type"] == "dir":
                    sort_children(c)

        sort_children(root)

        file_count = sum(1 for wf in rows if not wf.is_dir)
        return {
            **root,
            "count": file_count,
            "empty": file_count == 0,
            "truncated": file_count > settings.DEVSTUDIO_MAX_FILES,
        }

    def read_file(self, workspace_id: str, rel_path: str) -> dict[str, Any]:
        rel = _normalize_rel(rel_path)
        if not _is_editable(rel):
            raise ValueError(f"{rel} is not an editable text file")
        wf = self._one(workspace_id, rel)
        if wf is None or wf.is_dir:
            raise FileNotFoundError(f"{rel} not found")
        text = wf.content or ""
        size = wf.size or len(text.encode("utf-8"))
        if size > _max_file_bytes():
            raise ValueError(
                f"{rel} is {size // 1024} KB, above the "
                f"{settings.DEVSTUDIO_MAX_FILE_KB} KB editor limit"
            )
        return {
            "path": rel,
            "name": rel.rsplit("/", 1)[-1],
            "language": _language_for(rel),
            "content": text,
            "size": size,
            "editable": True,
            "hash": wf.content_hash or _content_hash(text),
            "updated_at": wf.updated_at.isoformat() if wf.updated_at else "",
        }

    def write_file(self, workspace_id: str, rel_path: str, content: str) -> dict[str, Any]:
        rel = _normalize_rel(rel_path)
        if not _is_editable(rel):
            raise ValueError(f"{rel} is not an editable text file")
        payload = content if isinstance(content, str) else ""
        encoded = payload.encode("utf-8")
        if len(encoded) > _max_file_bytes():
            raise ValueError(
                f"Content is {len(encoded) // 1024} KB, above the "
                f"{settings.DEVSTUDIO_MAX_FILE_KB} KB limit"
            )

        existing = self._one(workspace_id, rel)
        if existing is not None and existing.is_dir:
            raise ValueError(f"{rel} is a directory")

        now = datetime.now(timezone.utc)
        if existing is None:
            wf = WorkspaceFile(
                workspace_id=workspace_id,
                path=rel,
                is_dir=False,
                content=payload,
                size=len(encoded),
                content_hash=_content_hash(payload),
                created_at=now,
                updated_at=now,
            )
            self.db.add(wf)
            self._ensure_parent_dirs(workspace_id, rel)
            self.db.flush()
            self.db.commit()
        else:
            existing.content = payload
            existing.size = len(encoded)
            existing.content_hash = _content_hash(payload)
            existing.updated_at = now
            self.db.flush()
            self.db.commit()

        return {
            "path": rel,
            "name": rel.rsplit("/", 1)[-1],
            "language": _language_for(rel),
            "content": payload,
            "size": len(encoded),
            "editable": True,
            "hash": _content_hash(payload),
            "updated_at": now.isoformat(),
        }

    def create_file(self, workspace_id: str, rel_path: str, content: str = "") -> dict[str, Any]:
        rel = _normalize_rel(rel_path)
        existing = self._one(workspace_id, rel)
        if existing is not None:
            raise ValueError(f"{rel} already exists")
        return self.write_file(workspace_id, rel, content)

    def create_dir(self, workspace_id: str, rel_path: str) -> dict[str, Any]:
        rel = _normalize_rel(rel_path)
        existing = self._one(workspace_id, rel)
        if existing is not None and not existing.is_dir:
            raise ValueError(f"{rel} is a file")
        if existing is None:
            now = datetime.now(timezone.utc)
            self.db.add(WorkspaceFile(
                workspace_id=workspace_id,
                path=rel,
                is_dir=True,
                content=None,
                size=0,
                created_at=now,
                updated_at=now,
            ))
            self._ensure_parent_dirs(workspace_id, rel)
            self.db.flush()
            self.db.commit()
        return {"path": rel, "name": rel.rsplit("/", 1)[-1], "type": "dir"}

    def delete_entry(self, workspace_id: str, rel_path: str) -> dict[str, Any]:
        rel = _normalize_rel(rel_path)
        wf = self._one(workspace_id, rel)
        if wf is None:
            raise FileNotFoundError(f"{rel} not found")

        if wf.is_dir:
            # Delete this dir and all descendants (paths that start with rel/).
            prefix = rel + "/"
            descendants = [
                r for r in self._rows(workspace_id)
                if r.path.startswith(prefix)
            ]
            for r in descendants:
                self.db.delete(r)
            self.db.delete(wf)
            self.db.flush()
            self.db.commit()
            return {"path": rel, "type": "dir", "deleted": True}

        self.db.delete(wf)
        self.db.flush()
        self.db.commit()
        return {"path": rel, "type": "file", "deleted": True}

    def seed_sample(self, workspace_id: str) -> list[str]:
        from app.services.devstudio import SAMPLE_FILES

        created: list[str] = []
        for rel, content in SAMPLE_FILES.items():
            try:
                existing = self._one(workspace_id, rel)
            except Exception:
                existing = None
            if existing is not None:
                continue
            self.write_file(workspace_id, rel, content)
            created.append(rel)
        self.db.flush()
        return created

    def read_content(self, workspace_id: str, rel_path: str) -> str | None:
        try:
            rel = _normalize_rel(rel_path)
        except ValueError:
            return None
        wf = self._one(workspace_id, rel)
        if wf is None or wf.is_dir:
            return None
        return wf.content

    def file_exists(self, workspace_id: str, rel_path: str) -> bool:
        try:
            rel = _normalize_rel(rel_path)
        except ValueError:
            return False
        return self._one(workspace_id, rel) is not None

    def get_all_files(self, workspace_id: str) -> list[dict[str, Any]]:
        """Return all files as flat dicts (used by the Piston executor)."""
        rows = self._rows(workspace_id)
        return [
            {"path": wf.path, "content": wf.content or ""}
            for wf in rows
            if not wf.is_dir
        ]


# --------------------------------------------------------------------------
# Backend selection
# --------------------------------------------------------------------------


def get_store(db: Session | None = None) -> DiskStore | DbStore:
    """Return the active storage backend."""
    backend = os.getenv("DEVSTUDIO_BACKEND", settings.DEVSTUDIO_BACKEND).lower()
    if backend == "db":
        if db is None:
            raise RuntimeError("DEVSTUDIO_BACKEND=db requires a database session")
        return DbStore(db)
    return DiskStore()
