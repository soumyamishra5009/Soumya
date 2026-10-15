"""Live stack verification against a running API (real HTTP, no TestClient).

Proves the full Phase 1 contract: auth -> workspace -> meeting -> upload ->
audio stream -> tasks. Processing is not triggered here because that requires
a local Whisper model and an LLM (see tests/test_stt_live.py for STT).

Usage (from apps/api):  python tests/verify_live_stack.py [base_url]
"""

from __future__ import annotations

import io
import sys
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


def tiny_wav() -> bytes:
    return (
        b"RIFF" + b"\x24\x08\x00\x00" + b"WAVEfmt "
        + b"\x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00@\x1f\x00\x00\x02\x00\x10\x00"
        + b"data" + b"\x00\x00\x00\x00"
    )


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=15.0) as c:
        r = c.get("/health")
        check(
            "health",
            r.status_code == 200 and r.json().get("database") == "ok",
            str(r.json()),
        )

        email = f"live+{uuid.uuid4().hex[:8]}@example.com"
        r = c.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "secret123", "name": "Live Check"},
        )
        check("register", r.status_code == 201, f"status={r.status_code}")
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        r = c.get("/api/v1/auth/me", headers=h)
        check("me", r.status_code == 200 and r.json()["email"] == email, "")

        r = c.post("/api/v1/workspaces", headers=h, json={"name": "Live WS"})
        ws = r.json()["id"]
        check("create workspace", r.status_code == 201, r.json().get("slug", ""))

        r = c.post(
            "/api/v1/meetings",
            headers=h,
            json={
                "workspace_id": ws,
                "title": "Live Meeting",
                "participants": ["A", "B"],
                "consent_confirmed": True,
            },
        )
        mid = r.json()["id"]
        check("create meeting", r.status_code == 201, r.json().get("status", ""))

        r = c.post(
            f"/api/v1/meetings/{mid}/audio",
            headers=h,
            files={"file": ("live.wav", io.BytesIO(tiny_wav()), "audio/wav")},
        )
        check("upload audio", r.status_code == 200, r.json().get("audio_file_name", ""))

        r = c.get(f"/api/v1/meetings/{mid}/audio?token={token}")
        check(
            "stream audio",
            r.status_code == 200 and r.content.startswith(b"RIFF"),
            f"{len(r.content)} bytes",
        )

        r = c.post(
            "/api/v1/tasks",
            headers=h,
            json={"workspace_id": ws, "title": "Live task", "priority": "high"},
        )
        tid = r.json()["id"]
        check("create task", r.status_code == 201, r.json().get("status", ""))

        r = c.patch(f"/api/v1/tasks/{tid}", headers=h, json={"status": "done"})
        check(
            "complete task",
            r.status_code == 200 and r.json().get("completed_at") is not None,
            "",
        )

        r = c.get(f"/api/v1/workspaces/{ws}/tasks", headers=h)
        check("list tasks", r.status_code == 200 and len(r.json()) == 1, f"n={len(r.json())}")

        r = c.get(f"/api/v1/meetings/{mid}", headers=h)
        check("meeting detail", r.status_code == 200 and "transcript" in r.json(), "")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
