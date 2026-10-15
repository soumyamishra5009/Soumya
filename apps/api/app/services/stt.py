"""Speech-to-text service.

Engine selection:
- STT_ENGINE=whisper_local -> faster-whisper (free, local, CPU-friendly)
- STT_ENGINE=groq_whisper  -> Groq Whisper API (free tier, fast)

Both return a uniform shape:
{
  "full_text": str,
  "segments": [{"start": float, "end": float, "text": str, "speaker": str|None}],
  "language": str,
  "duration_seconds": float,
  "engine": str,
  "model": str,
}
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_whisper_model = None
_whisper_loaded = False
_av_compat_ready = False


def _install_av_compat() -> None:
    """Shim for PyAV/faster-whisper version drift.

    faster-whisper (<= 1.1.x) calls ``av.open(..., metadata_errors="ignore")``,
    but that keyword was removed in newer PyAV releases, raising
    ``TypeError: open() got an unexpected keyword argument 'metadata_errors'``.
    We wrap ``av.open`` to drop keywords the installed PyAV does not accept.
    """
    global _av_compat_ready
    if _av_compat_ready:
        return
    try:
        import av
    except Exception:  # av not installed at all -> faster-whisper will fail loudly
        _av_compat_ready = True
        return

    if getattr(av, "_syncforge_compat", False):
        _av_compat_ready = True
        return

    _original_open = av.open

    def _patched_open(*args, **kwargs):
        try:
            return _original_open(*args, **kwargs)
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            # Strip whichever keyword PyAV rejected and retry.
            import re

            bad = re.findall(r"unexpected keyword argument '([^']+)'", str(exc))
            for name in bad:
                kwargs.pop(name, None)
            if not bad:
                raise
            return _original_open(*args, **kwargs)

    av.open = _patched_open  # type: ignore[assignment]
    av._syncforge_compat = True  # type: ignore[attr-defined]
    _av_compat_ready = True
    logger.debug("Installed PyAV compatibility shim for faster-whisper")


def _get_local_model():
    """Lazy-load the faster-whisper model (first call is slow)."""
    global _whisper_model, _whisper_loaded
    if _whisper_loaded:
        return _whisper_model

    try:
        from faster_whisper import WhisperModel  # type: ignore

        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        model_size = os.getenv("WHISPER_MODEL", "small")
        _whisper_model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("faster-whisper model loaded: %s (%s/%s)", model_size, device, compute_type)
    except Exception as exc:  # pragma: no cover - depends on local environment
        logger.warning("Could not load faster-whisper: %s", exc)
        _whisper_model = None

    _whisper_loaded = True
    return _whisper_model


def _transcribe_local(audio_path: str) -> dict[str, Any]:
    _install_av_compat()
    model = _get_local_model()
    if model is None:
        raise RuntimeError("faster-whisper model unavailable")

    segments_iter, info = model.transcribe(audio_path, vad_filter=True, beam_size=1)
    segments: list[dict[str, Any]] = []
    full_text_parts: list[str] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": text,
            "speaker": None,
            "confidence": float(getattr(seg, "avg_logprob", None) + 1) if getattr(seg, "avg_logprob", None) is not None else None,
        })
        full_text_parts.append(text)

    duration = float(getattr(info, "duration", 0.0) or 0.0)
    language = str(getattr(info, "language", "") or "")
    return {
        "full_text": " ".join(full_text_parts),
        "segments": segments,
        "language": language,
        "duration_seconds": duration,
        "engine": "whisper_local",
        "model": os.getenv("WHISPER_MODEL", "small"),
    }


def _transcribe_groq(audio_path: str) -> dict[str, Any]:
    """Groq Whisper API transcription (free tier)."""
    import httpx  # local import

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not configured")

    model_name = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")
    with open(audio_path, "rb") as fh:
        files = {"file": (os.path.basename(audio_path), fh, "audio/mpeg")}
        data = {"model": model_name, "response_format": "verbose_json"}
        resp = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
            timeout=120.0,
        )
    resp.raise_for_status()
    payload = resp.json()

    segments_raw = payload.get("segments") or []
    segments = [
        {
            "start": float(s.get("start", 0)),
            "end": float(s.get("end", 0)),
            "text": str(s.get("text", "")).strip(),
            "speaker": None,
            "confidence": None,
        }
        for s in segments_raw
        if str(s.get("text", "")).strip()
    ]

    return {
        "full_text": str(payload.get("text", "")),
        "segments": segments,
        "language": str(payload.get("language", "")),
        "duration_seconds": float(payload.get("duration") or 0.0),
        "engine": "groq_whisper",
        "model": model_name,
    }


def transcribe(audio_path: str, engine: str | None = None) -> dict[str, Any]:
    """Transcribe an audio file. Raises on failure (caller handles fallback)."""
    engine = engine or os.getenv("STT_ENGINE", "whisper_local")
    if engine == "groq_whisper":
        return _transcribe_groq(audio_path)
    return _transcribe_local(audio_path)


def transcribe_with_fallback(audio_path: str) -> dict[str, Any]:
    """Try the configured engine, then fall back to the other one.

    Raises RuntimeError if neither engine can produce a transcript.
    """
    primary = os.getenv("STT_ENGINE", "whisper_local")
    errors: list[str] = []

    for engine in ([primary] if primary == "groq_whisper" else ["whisper_local", "groq_whisper"]):
        try:
            return transcribe(audio_path, engine=engine)
        except Exception as exc:
            logger.warning("STT engine %s failed: %s", engine, exc)
            errors.append(f"{engine}: {exc}")

    raise RuntimeError("All STT engines failed -> " + " | ".join(errors))
