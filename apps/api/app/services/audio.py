"""Audio metadata helpers (duration probing).

Kept dependency-light: uses the stdlib ``wave`` module for WAV and falls back
to PyAV for everything else (mp3, m4a, flac, ogg, webm, mp4...). Probing reads
container metadata only — no full decode — so it is cheap and safe to run on
upload.
"""

from __future__ import annotations

import logging
import wave

logger = logging.getLogger(__name__)


def _probe_wav(path: str) -> float | None:
    try:
        with wave.open(path, "rb") as w:
            rate = w.getframerate()
            if not rate:
                return None
            return round(w.getnframes() / float(rate), 3)
    except Exception:
        return None


def _probe_av(path: str) -> float | None:
    try:
        import av
    except Exception:
        return None

    try:
        with av.open(path, mode="r") as container:
            if container.duration is not None:
                # PyAV reports container duration in microseconds
                return round(container.duration / 1_000_000, 3)
            for stream in container.streams:
                if stream.duration is not None and stream.time_base is not None:
                    return round(float(stream.duration * stream.time_base), 3)
    except Exception as exc:
        logger.debug("PyAV could not probe duration for %s: %s", path, exc)
    return None


def probe_duration_seconds(path: str) -> float | None:
    """Return the media duration in seconds, or None if it cannot be read."""
    duration = _probe_wav(path)
    if duration is not None:
        return duration
    return _probe_av(path)
