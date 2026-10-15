"""Full pipeline with NO LLM reachable: offline fallback must still complete.

Patches STT (so no Whisper model needed) and forces the LLM call to fail, then
verifies the offline extractive fallback still produces a summary, decisions
and tasks end-to-end.

Run from apps/api:  python tests/test_fallback_pipeline.py
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import uuid

# Windows consoles default to cp1252; the fallback summary uses emoji.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # pragma: no cover
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = os.path.join(tempfile.gettempdir(), f"fallback_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.replace(os.sep, '/')}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.core.database import init_db  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services import stt as stt_service  # noqa: E402
from app.services import meeting_summary as ms  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


TRANSCRIPT_TEXT = (
    "Okay team, let's start the sprint planning meeting. "
    "First decision, we will ship the login page by Friday. "
    "Second decision, Google authentication must be added this sprint. "
    "Priya will redesign the dashboard layout. "
    "Rahul will finish the login page and write the tests. "
    "There is a risk that testing starts late and blocks the release. "
    "Open question, who will own the production deployment? "
    "Next steps, daily standup at 10 a.m. and a demo on Monday."
)

FAKE_TRANSCRIPT = {
    "full_text": TRANSCRIPT_TEXT,
    "segments": [
        {"start": 0.0, "end": 5.0, "text": "Okay team, let's start the sprint planning meeting.", "speaker": "S1"},
        {"start": 5.0, "end": 12.0, "text": "First decision, we will ship the login page by Friday.", "speaker": "S1"},
        {"start": 12.0, "end": 17.0, "text": "Priya will redesign the dashboard layout.", "speaker": "S2"},
    ],
    "language": "en",
    "duration_seconds": 17.0,
    "engine": "whisper_local",
    "model": "small",
}


def fake_stt(audio_path: str):
    return dict(FAKE_TRANSCRIPT)


def boom_llm(*args, **kwargs):
    raise ConnectionError("Could not connect to Ollama at http://localhost:11434")


def tiny_wav() -> bytes:
    return (
        b"RIFF" + b"\x24\x08\x00\x00" + b"WAVEfmt "
        + b"\x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00@\x1f\x00\x00\x02\x00\x10\x00"
        + b"data" + b"\x00\x00\x00\x00"
    )


def run() -> int:
    init_db()

    # Force the "no LLM available" path, but keep the fallback enabled
    stt_service.transcribe_with_fallback = fake_stt  # type: ignore[assignment]
    ms.structured_completion = boom_llm  # type: ignore[assignment]
    settings.ALLOW_EXTRACTIVE_FALLBACK = True

    c = TestClient(main.app)

    email = f"fb+{uuid.uuid4().hex[:6]}@example.com"
    tok = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": "Fallback"},
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    ws = c.post("/api/v1/workspaces", headers=h, json={"name": "Fallback WS"}).json()["id"]

    m = c.post(
        "/api/v1/meetings",
        headers=h,
        json={
            "workspace_id": ws,
            "title": "Sprint Planning",
            "participants": ["Priya", "Rahul"],
            "consent_confirmed": True,
        },
    ).json()
    mid = m["id"]

    r = c.post(
        f"/api/v1/meetings/{mid}/audio",
        headers=h,
        files={"file": ("m.wav", io.BytesIO(tiny_wav()), "audio/wav")},
    )
    check("upload audio", r.status_code == 200, f"status={r.status_code}")

    r = c.post(f"/api/v1/meetings/{mid}/process", headers=h)
    check("process", r.status_code == 200, f"status={r.status_code}")

    detail = c.get(f"/api/v1/meetings/{mid}", headers=h).json()
    check("status completed (not failed)", detail["status"] == "completed", detail["status"])
    check(
        "no error message",
        not detail.get("error_message"),
        str(detail.get("error_message")),
    )

    summary = detail.get("summary") or ""
    check("summary produced", len(summary) > 20, summary[:70])
    check(
        "summary is marked as offline fallback",
        summary.startswith("⚠️ Offline extractive summary"),
        summary[:70],
    )

    check(
        "decisions extracted",
        len(detail.get("decisions") or []) > 0,
        f"n={len(detail.get('decisions') or [])}",
    )
    check(
        "key points extracted",
        len(detail.get("key_points") or []) > 0,
        f"n={len(detail.get('key_points') or [])}",
    )
    check(
        "risks extracted",
        len(detail.get("risks") or []) > 0,
        f"n={len(detail.get('risks') or [])}",
    )
    check(
        "unanswered questions extracted",
        len(detail.get("unanswered_questions") or []) > 0,
        f"n={len(detail.get('unanswered_questions') or [])}",
    )

    tasks = c.get(f"/api/v1/meetings/{mid}/tasks", headers=h).json()
    check("tasks created", len(tasks) > 0, f"n={len(tasks)}")
    titles = " | ".join(t["title"].lower() for t in tasks)
    check("assignee task present", "priya" in titles or "rahul" in titles, titles)
    check(
        "tasks linked to meeting",
        all(t["meeting_id"] == mid for t in tasks),
        "",
    )

    board = c.get(f"/api/v1/workspaces/{ws}/tasks", headers=h).json()
    check("tasks on the board", len(board) == len(tasks), f"{len(board)} vs {len(tasks)}")

    # Re-running with fallback disabled must fail loudly
    settings.ALLOW_EXTRACTIVE_FALLBACK = False
    m2 = c.post(
        "/api/v1/meetings",
        headers=h,
        json={"workspace_id": ws, "title": "Second", "consent_confirmed": True},
    ).json()
    c.post(
        f"/api/v1/meetings/{m2['id']}/audio",
        headers=h,
        files={"file": ("m.wav", io.BytesIO(tiny_wav()), "audio/wav")},
    )
    c.post(f"/api/v1/meetings/{m2['id']}/process", headers=h)
    d2 = c.get(f"/api/v1/meetings/{m2['id']}", headers=h).json()
    check(
        "fallback disabled -> meeting fails loudly",
        d2["status"] == "failed",
        f"{d2['status']} / {d2.get('error_message')}",
    )

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
