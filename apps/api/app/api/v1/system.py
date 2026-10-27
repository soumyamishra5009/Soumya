from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.deps import get_current_user

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def get_system_status(current_user=Depends(get_current_user)) -> Dict[str, Any]:
    """Get provider/status information for dashboard/settings."""
    gemini_ok = bool(getattr(settings, "GEMINI_API_KEY", ""))
    openrouter_ok = bool(getattr(settings, "OPENROUTER_API_KEY", ""))
    ollama_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_ok = False
    try:
        import httpx

        resp = httpx.get(f"{ollama_url}/api/tags", timeout=2.0)
        if resp.status_code == 200:
            ollama_ok = True
    except Exception:
        ollama_ok = False

    stt_engine = getattr(settings, "STT_ENGINE", "whisper_local")
    whisper_ok = False
    if stt_engine == "whisper_local":
        try:
            import faster_whisper  # type: ignore

            whisper_ok = True
        except Exception:
            whisper_ok = False

    ffmpeg_ok = shutil.which("ffmpeg") is not None
    git_ok = shutil.which("git") is not None

    return {
        "llm": {
            "provider_order": getattr(settings, "LLM_PROVIDER_ORDER", ""),
            "gemini": {"configured": gemini_ok, "model": getattr(settings, "GEMINI_MODEL", "")},
            "openrouter": {"configured": openrouter_ok, "model": getattr(settings, "OPENROUTER_MODEL", "")},
            "ollama": {"configured": ollama_ok, "base_url": ollama_url, "model": getattr(settings, "DEFAULT_CHAT_MODEL", "")},
        },
        "stt": {
            "engine": stt_engine,
            "whisper_model": getattr(settings, "WHISPER_MODEL", "") if stt_engine == "whisper_local" else None,
            "whisper_available": whisper_ok,
            "gemini_configured": gemini_ok if stt_engine == "gemini" else gemini_ok,
        },
        "env": {
            "database_url_scheme": settings.DATABASE_URL.split("://")[0] if "://" in settings.DATABASE_URL else "unknown",
            "executor": getattr(settings, "CODE_EXECUTOR", "local"),
            "devstudio_backend": getattr(settings, "DEVSTUDIO_BACKEND", "disk"),
        },
        "tools": {"ffmpeg": ffmpeg_ok, "git": git_ok},
    }
