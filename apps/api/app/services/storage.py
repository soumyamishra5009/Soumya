"""Local file storage for meeting audio uploads."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from app.core.config import settings

ALLOWED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".webm", ".mp4", ".aac"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}


def _safe_name(name: str) -> str:
    name = os.path.basename(name or "upload")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name[:100] or "upload"


def save_audio(file_bytes: bytes, filename: str) -> str:
    """Persist an uploaded file under UPLOAD_DIR/<uuid>/<safe_name>.

    Returns the absolute path.
    """
    upload_dir = Path(settings.UPLOAD_DIR)
    folder = upload_dir / str(uuid.uuid4())
    folder.mkdir(parents=True, exist_ok=True)

    safe = _safe_name(filename)
    path = folder / safe
    path.write_bytes(file_bytes)

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if path.stat().st_size > max_bytes:
        path.unlink()
        raise ValueError(f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit")

    return str(path.resolve())


def validate_filename(filename: str) -> bool:
    ext = os.path.splitext(filename or "")[1].lower()
    return ext in (ALLOWED_AUDIO_EXTS | ALLOWED_VIDEO_EXTS)


def delete_file(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
