"""Live end-to-end demo against the RUNNING API: real speech -> real STT -> AI/offline extraction -> tasks.

Uses tests/sample-meeting.wav (generate it with make-sample-audio.ps1).

    python tests/verify_live_e2e.py [base_url]
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

import httpx  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SAMPLE = Path(__file__).with_name("sample-meeting.wav")

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


def main() -> int:
    if not SAMPLE.exists():
        print(f"FAIL | sample audio missing: {SAMPLE}")
        print("Create it first: powershell -File tests\\make-sample-audio.ps1")
        return 1

    with httpx.Client(base_url=BASE, timeout=30.0) as c:
        r = c.get("/health")
        check("api up", r.status_code == 200, str(r.json()))
        if r.status_code != 200:
            return 1

        email = f"e2e+{uuid.uuid4().hex[:8]}@example.com"
        tok = c.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "secret123", "name": "E2E Demo"},
        ).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        check("registered", True, email)

        ws = c.post("/api/v1/workspaces", headers=h, json={"name": "E2E Workspace"}).json()["id"]
        check("workspace created", True, ws)

        m = c.post(
            "/api/v1/meetings",
            headers=h,
            json={
                "workspace_id": ws,
                "title": "Sprint Planning (live demo)",
                "description": "Real Windows TTS sample, real Whisper STT.",
                "participants": ["Parth", "Saumya", "Rahul"],
                "consent_confirmed": True,
            },
        ).json()
        mid = m["id"]
        check("meeting created", True, mid)

        with SAMPLE.open("rb") as fh:
            r = c.post(
                f"/api/v1/meetings/{mid}/audio",
                headers=h,
                files={"file": ("sample-meeting.wav", fh, "audio/wav")},
            )
        check("audio uploaded", r.status_code == 200, r.json().get("audio_file_name", ""))
        check(
            "duration detected",
            (r.json().get("audio_duration_seconds") or 0) > 1,
            str(r.json().get("audio_duration_seconds")),
        )

        r = c.post(f"/api/v1/meetings/{mid}/process", headers=h)
        check("process accepted", r.status_code == 200, r.json().get("status", ""))

        # Poll until finished
        deadline = time.time() + 600
        detail: dict = {}
        while time.time() < deadline:
            detail = c.get(f"/api/v1/meetings/{mid}", headers=h).json()
            status = detail.get("status")
            if status in {"completed", "failed"}:
                break
            print(f"  ... status={status}")
            time.sleep(5)

        status = detail.get("status")
        check("pipeline finished", status in {"completed", "failed"}, str(status))
        if status != "completed":
            print("error:", detail.get("error_message"))
            return 1

        print("\n================ SUMMARY ================")
        print(detail.get("summary"))
        print("\n------------- KEY POINTS -------------")
        for p in detail.get("key_points") or []:
            print(f"  - {p}")
        print("\n------------- DECISIONS -------------")
        for d in detail.get("decisions") or []:
            print(f"  - [{d['impact']}] {d['title']}")
        print("\n------------- RISKS -------------")
        for x in detail.get("risks") or []:
            print(f"  - {x}")
        print("\n------------- QUESTIONS -------------")
        for q in detail.get("unanswered_questions") or []:
            print(f"  - {q}")

        segments = (detail.get("transcript") or {}).get("segments") or []
        print(f"\n------------- TRANSCRIPT ({len(segments)} segments) -------------")
        for s in segments:
            who = f"{s['speaker']}: " if s.get("speaker") else ""
            print(f"  {who}{s['text']}")

        tasks = c.get(f"/api/v1/meetings/{mid}/tasks", headers=h).json()
        print(f"\n------------- TASKS ({len(tasks)}) -------------")
        for t in tasks:
            print(f"  - [{t['priority']}] {t['title']}")

        check("transcript segments", len(segments) > 0, f"n={len(segments)}")
        check("summary produced", bool(detail.get("summary")), "")
        check("decisions produced", len(detail.get("decisions") or []) > 0, f"n={len(detail.get('decisions') or [])}")
        check("tasks produced", len(tasks) > 0, f"n={len(tasks)}")

        words = (detail.get("transcript") or {}).get("full_text", "").lower()
        check(
            "speech recognized",
            "login" in words or "sprint" in words,
            words[:60],
        )

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n================ RESULT ================")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
