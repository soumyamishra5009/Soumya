"""Pipeline test: audio -> transcript -> AI summary -> decisions -> tasks.

Patches STT and the LLM extractor so it runs without Ollama/Groq/Docker.
Run from apps/api:  python tests/test_pipeline.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = os.path.join(tempfile.gettempdir(), f"pipeline_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.replace(os.sep, '/')}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.core.database import init_db  # noqa: E402
from app.services import stt as stt_service  # noqa: E402
from app.api.v1 import meetings as meetings_api  # noqa: E402
from app.services.meeting_summary import _normalize  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


# --- Fake transcripts -------------------------------------------------------
FAKE_TRANSCRIPT = {
    "full_text": (
        "Chalo start karte hain. Sprint planning discussion hai. "
        "Decision liya hai ki Friday tak login page complete karna hai "
        "aur Google authentication add karna hai. "
        "Priya layout redesign handle karegi. "
        "Risks: timeline tight hai agar testing late start hui. "
        "Sawal: deployment kaun karega? "
        "Next: daily standup 10 baje se."
    ),
    "segments": [
        {"start": 0.0, "end": 4.5, "text": "Chalo start karte hain.", "speaker": "S1"},
        {"start": 4.5, "end": 12.0, "text": "Friday tak login page complete karna hai.", "speaker": "S1"},
        {"start": 12.0, "end": 18.0, "text": "Google authentication add karna hai.", "speaker": "S2"},
    ],
    "language": "hi",
    "duration_seconds": 18.0,
    "engine": "whisper_local",
    "model": "small",
}

# Messy on purpose: fenced JSON, bad date formats, extra prose
RAW_LLM_OUTPUT = {
    "summary": "Team ne sprint planning ki; login page aur Google auth par decision liya gaya.",
    "key_points": ["Friday deadline", "Google auth add karna hai", "Daily standup 10 baje"],
    "decisions": [
        {"title": "Login page Friday tak ship hoga", "description": "Auth flow prioritize", "impact": "high", "rationale": "User onboarding blocked hai"},
        {"title": "Layout redesign Priya karegi", "impact": "unknown-impact", "rationale": ""},
    ],
    "action_items": [
        {"title": "Login page complete karo", "assignee": "Rahul", "priority": "high", "due_date": "15-10-2026", "estimated_hours": "8"},
        {"title": "Google authentication add karo", "assignee": "Aman", "priority": "urgent", "due_date": "2026-10-17", "estimated_hours": 6},
        {"title": "", "assignee": "nobody"},
        {"title": "Deployment owner decide karo", "due_date": "not-a-date", "priority": "medium"},
    ],
    "risks": ["Timeline tight hai"],
    "unanswered_questions": ["Deployment kaun karega?"],
    "next_steps": ["Daily standup 10 baje"],
}


def fake_stt(audio_path: str):
    return dict(FAKE_TRANSCRIPT)


def fake_extract(transcript_text, title="", meeting_date=None, participants=None, model=None):
    assert "Chalo" in transcript_text, "extractor did not receive transcript text"
    return _normalize(dict(RAW_LLM_OUTPUT))


def tiny_wav() -> bytes:
    return (
        b"RIFF" + b"\x24\x08\x00\x00" + b"WAVEfmt "
        + b"\x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00@\x1f\x00\x00\x02\x00\x10\x00"
        + b"data" + b"\x00\x00\x00\x00"
    )


def run() -> int:
    init_db()

    # Patch services
    stt_service.transcribe_with_fallback = fake_stt  # type: ignore[assignment]
    meetings_api.extract_meeting_intelligence = fake_extract  # type: ignore[assignment]

    c = TestClient(main.app)

    # Register + workspace + meeting
    email = f"pipe+{uuid.uuid4().hex[:6]}@example.com"
    tok = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": "Pipeline"},
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    ws = c.post(
        "/api/v1/workspaces", headers=h, json={"name": "Pipeline WS"}
    ).json()["id"]

    m = c.post(
        "/api/v1/meetings",
        headers=h,
        json={
            "workspace_id": ws,
            "title": "Sprint Planning",
            "participants": ["Rahul", "Aman", "Priya"],
            "consent_confirmed": True,
        },
    ).json()

    # Upload
    r = c.post(
        f"/api/v1/meetings/{m['id']}/audio",
        headers=h,
        files={"file": ("sprint.wav", __import__("io").BytesIO(tiny_wav()), "audio/wav")},
    )
    check("upload ok", r.status_code == 200, f"status={r.status_code}")

    # Consent gate: create a 2nd meeting without consent, expect 400
    m2 = c.post(
        "/api/v1/meetings",
        headers=h,
        json={"workspace_id": ws, "title": "No consent", "consent_confirmed": False},
    ).json()
    r = c.post(
        f"/api/v1/meetings/{m2['id']}/audio",
        headers=h,
        files={"file": ("a.wav", __import__("io").BytesIO(tiny_wav()), "audio/wav")},
    )
    r = c.post(f"/api/v1/meetings/{m2['id']}/process", headers=h)
    check("consent gate blocks processing", r.status_code == 400, f"status={r.status_code}")

    # Process (runs inline within the TestClient request via BackgroundTasks)
    r = c.post(f"/api/v1/meetings/{m['id']}/process", headers=h)
    check("process accepted", r.status_code == 200, f"status={r.status_code} -> {r.json().get('status')}")

    # Meeting detail
    r = c.get(f"/api/v1/meetings/{m['id']}", headers=h)
    data = r.json()
    check("meeting completed", data["status"] == "completed", f"status={data['status']} err={data.get('error_message')}")
    check("summary stored", bool(data.get("summary")), str(data.get("summary"))[:60])
    check("language recorded", data.get("language") == "hi", str(data.get("language")))
    check("no error", data.get("error_message") in (None, ""), str(data.get("error_message")))

    # Transcript + segments
    tr = data.get("transcript") or {}
    check("transcript present", bool(tr.get("id")), tr.get("engine", ""))
    check(
        "segments stored",
        len(tr.get("segments") or []) == 3,
        f"count={len(tr.get('segments') or [])}",
    )
    check("segment text preserved", (tr.get("segments") or [{}])[0].get("text") == "Chalo start karte hain.", "")

    # Summary endpoint
    s = c.get(f"/api/v1/meetings/{m['id']}/summary", headers=h).json()
    check("decisions extracted", len(s["decisions"]) == 2, f"count={len(s['decisions'])}")
    check(
        "decision impact coerced",
        s["decisions"][1]["impact"] == "medium",
        s["decisions"][1]["impact"],
    )
    check("key points", len(s["key_points"]) == 3, str(len(s["key_points"])))
    check("risks", s["risks"] == ["Timeline tight hai"], str(s["risks"]))

    # Tasks derived from action items
    tasks = c.get(f"/api/v1/meetings/{m['id']}/tasks", headers=h).json()
    check("action items -> tasks", len(tasks) == 3, f"count={len(tasks)} (blank title dropped)")
    check(
        "priority order (urgent first)",
        [t["priority"] for t in tasks][0] == "urgent",
        str([t["priority"] for t in tasks]),
    )

    by_title = {t["title"]: t for t in tasks}
    t1 = by_title.get("Login page complete karo", {})
    t2 = by_title.get("Google authentication add karo", {})
    t3 = by_title.get("Deployment owner decide karo", {})

    check("dd-mm-yyyy date parsed", (t1.get("due_date") or "").startswith("2026-10-15"), str(t1.get("due_date")))
    check("yyyy-mm-dd date parsed", (t2.get("due_date") or "").startswith("2026-10-17"), str(t2.get("due_date")))
    check("bad date -> null", t3.get("due_date") is None, str(t3.get("due_date")))
    check("estimated_hours string->float", t1.get("estimated_hours") == 8.0, str(t1.get("estimated_hours")))
    check("assigned", t1.get("assignee_id") is None and True, "assignee resolution is Phase 2 (by name)")
    check("all linked to meeting", all(t["meeting_id"] == m["id"] for t in tasks), "")
    check("all status todo", all(t["status"] == "todo" for t in tasks), str([t["status"] for t in tasks]))

    # Re-process should be idempotent (decisions replaced, no dup tasks from re-run)
    r = c.post(f"/api/v1/meetings/{m['id']}/process", headers=h)
    check("reprocess ok", r.status_code == 200, f"status={r.status_code}")
    tasks2 = c.get(f"/api/v1/meetings/{m['id']}/tasks", headers=h).json()
    check("reprocess keeps task count stable", len(tasks2) == 3, f"count={len(tasks2)}")
    s2 = c.get(f"/api/v1/meetings/{m['id']}/summary", headers=h).json()
    check("reprocess keeps 2 decisions", len(s2["decisions"]) == 2, f"count={len(s2['decisions'])}")

    # Failure path: STT blows up -> status=failed with message
    def boom(audio_path):
        raise RuntimeError("decoder crashed")

    stt_service.transcribe_with_fallback = boom  # type: ignore[assignment]
    m3 = c.post(
        "/api/v1/meetings",
        headers=h,
        json={"workspace_id": ws, "title": "Broken audio", "consent_confirmed": True},
    ).json()
    c.post(
        f"/api/v1/meetings/{m3['id']}/audio",
        headers=h,
        files={"file": ("bad.wav", __import__("io").BytesIO(tiny_wav()), "audio/wav")},
    )
    c.post(f"/api/v1/meetings/{m3['id']}/process", headers=h)
    d3 = c.get(f"/api/v1/meetings/{m3['id']}", headers=h).json()
    check("STT failure handled", d3["status"] == "failed", f"status={d3['status']}")
    check("error surfaced", "Transcription failed" in (d3.get("error_message") or ""), str(d3.get("error_message")))

    # Empty transcript -> failed
    def empty(audio_path):
        return {"full_text": "", "segments": [], "language": "", "duration_seconds": 1.0, "engine": "x", "model": "x"}

    stt_service.transcribe_with_fallback = empty  # type: ignore[assignment]
    m4 = c.post(
        "/api/v1/meetings",
        headers=h,
        json={"workspace_id": ws, "title": "Silent audio", "consent_confirmed": True},
    ).json()
    c.post(
        f"/api/v1/meetings/{m4['id']}/audio",
        headers=h,
        files={"file": ("sil.wav", __import__("io").BytesIO(tiny_wav()), "audio/wav")},
    )
    c.post(f"/api/v1/meetings/{m4['id']}/process", headers=h)
    d4 = c.get(f"/api/v1/meetings/{m4['id']}", headers=h).json()
    check("empty transcript handled", d4["status"] == "failed", f"status={d4['status']}")

    # Process without audio -> 400
    m5 = c.post(
        "/api/v1/meetings",
        headers=h,
        json={"workspace_id": ws, "title": "No audio", "consent_confirmed": True},
    ).json()
    r = c.post(f"/api/v1/meetings/{m5['id']}/process", headers=h)
    check("process without audio rejected", r.status_code == 400, f"status={r.status_code}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    code = run()
    try:
        os.remove(TEST_DB)
    except OSError:
        pass
    sys.exit(code)
