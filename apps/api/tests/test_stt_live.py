"""Opt-in live STT check: does faster-whisper actually load and run locally?

Downloads the `tiny` model (~75 MB) on first run, so it is NOT part of the
default test suite. Run explicitly:

    venv\\Scripts\\python.exe tests\\test_stt_live.py

A silent clip is expected to produce empty/whitespace text without raising.
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use the smallest model to keep the download quick
os.environ.setdefault("WHISPER_MODEL", "tiny")
os.environ.setdefault("WHISPER_DEVICE", "cpu")
os.environ.setdefault("WHISPER_COMPUTE_TYPE", "int8")
os.environ.setdefault("STT_ENGINE", "whisper_local")


def make_silence_wav(path: str, seconds: float = 2.0, rate: int = 16000) -> None:
    frames = int(seconds * rate)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<" + "h" * frames, *([0] * frames)))


def main() -> int:
    from app.services import stt

    # Prefer the real spoken sample if present (see make-sample-audio.ps1)
    sample = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "sample-meeting.wav"
    )
    if os.path.exists(sample):
        tmp_name = sample
        expect_speech = True
        print(f"clip: {sample} (spoken sample)")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        make_silence_wav(tmp.name)
        tmp_name = tmp.name
        expect_speech = False
        print(f"clip: {tmp_name} (silence fallback)")

    print(f"engine: {os.environ['STT_ENGINE']}  model: {os.environ['WHISPER_MODEL']}")

    try:
        result = stt.transcribe(tmp_name)
    except Exception as exc:
        print(f"FAIL | transcription raised: {type(exc).__name__}: {exc}")
        if not expect_speech:
            os.unlink(tmp_name)
        return 1

    print(f"engine -> {result.get('engine')}")
    print(f"model  -> {result.get('model')}")
    print(f"lang   -> {result.get('language')!r}")
    print(f"dur    -> {result.get('duration_seconds')}")
    print(f"segs   -> {len(result.get('segments') or [])}")
    print("text   ->")
    print(result.get("full_text"))

    ok = (
        result.get("engine") == "whisper_local"
        and isinstance(result.get("full_text"), str)
        and isinstance(result.get("segments"), list)
    )

    if expect_speech:
        text = (result.get("full_text") or "").lower()
        # The TTS script says "sprint planning" and "login page"
        heard = "sprint" in text or "planning" in text or "login" in text
        print(("PASS" if heard else "FAIL") + " | recognized expected words from speech")
        ok = ok and heard
    else:
        print("PASS | ran on silence without raising")

    if not expect_speech:
        os.unlink(tmp_name)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
