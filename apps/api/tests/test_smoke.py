"""End-to-end smoke test for the Phase 1 API (SQLite, no external services).

Run from apps/api:  python tests/test_smoke.py
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use a throwaway SQLite DB for the test
TEST_DB = os.path.join(tempfile.gettempdir(), f"test_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.replace(os.sep, '/')}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


def tiny_wav(seconds: float = 1.0, rate: int = 8000) -> bytes:
    # A valid mono 16-bit silent WAV so upload validation and duration probing
    # both have realistic input.
    frames = int(seconds * rate)
    pcm = b"\x00\x00" * frames
    data_size = len(pcm)
    fmt = (
        b"\x10\x00\x00\x00\x01\x00\x01\x00"
        + rate.to_bytes(4, "little")
        + (rate * 2).to_bytes(4, "little")
        + b"\x02\x00\x10\x00"
    )
    riff_size = 4 + (8 + len(fmt)) + (8 + data_size)
    return (
        b"RIFF"
        + riff_size.to_bytes(4, "little")
        + b"WAVEfmt "
        + fmt
        + b"data"
        + data_size.to_bytes(4, "little")
        + pcm
    )


def run() -> int:
    # Create tables directly (TestClient without `with` skips lifespan)
    from app.core.database import init_db

    init_db()
    c = TestClient(main.app)

    # --- health ---
    r = c.get("/health")
    check("health", r.status_code == 200 and r.json().get("status") == "healthy", str(r.json()))

    # --- register ---
    email = f"parth+{uuid.uuid4().hex[:6]}@example.com"
    r = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": "Parth"},
    )
    token = r.json().get("access_token", "") if r.status_code == 201 else ""
    check("register", r.status_code == 201 and token, f"status={r.status_code}")
    if not token:
        return 1
    h = {"Authorization": f"Bearer {token}"}

    # --- duplicate register rejected ---
    r2 = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": "Dup"},
    )
    check("duplicate register rejected", r2.status_code == 400, f"status={r2.status_code}")

    # --- login (json) ---
    r = c.post("/api/v1/auth/login", json={"email": email, "password": "secret123"})
    check("login", r.status_code == 200 and r.json().get("access_token"), f"status={r.status_code}")

    # --- bad login rejected ---
    r = c.post("/api/v1/auth/login", json={"email": email, "password": "wrongpass"})
    check("bad login rejected", r.status_code == 401, f"status={r.status_code}")

    # --- me ---
    r = c.get("/api/v1/auth/me", headers=h)
    check("me", r.status_code == 200 and r.json()["email"] == email, r.json().get("email", ""))

    # --- unauthorized rejected ---
    r = c.get("/api/v1/auth/me")
    check("unauthorized rejected", r.status_code == 401, f"status={r.status_code}")

    # --- workspace ---
    r = c.post(
        "/api/v1/workspaces",
        headers=h,
        json={"name": "Cognix Demo", "description": "test ws"},
    )
    ws = r.json().get("id", "")
    check("create workspace", r.status_code == 201 and ws, f"slug={r.json().get('slug')}")

    r = c.get("/api/v1/workspaces", headers=h)
    check("list workspaces", r.status_code == 200 and len(r.json()) == 1, f"count={len(r.json())}")

    # --- meeting ---
    r = c.post(
        "/api/v1/meetings",
        headers=h,
        json={
            "workspace_id": ws,
            "title": "Sprint Planning",
            "participants": ["Parth", "Saumya"],
            "consent_confirmed": True,
        },
    )
    mid = r.json().get("id", "")
    check("create meeting", r.status_code == 201 and mid, f"status={r.json().get('status')}")

    # --- upload audio ---
    r = c.post(
        f"/api/v1/meetings/{mid}/audio",
        headers=h,
        files={"file": ("sprint.wav", io.BytesIO(tiny_wav()), "audio/wav")},
    )
    check(
        "upload audio",
        r.status_code == 200 and r.json().get("audio_file_name") == "sprint.wav",
        f"status={r.status_code}",
    )
    check(
        "duration probed on upload",
        abs((r.json().get("audio_duration_seconds") or 0) - 1.0) < 0.05,
        str(r.json().get("audio_duration_seconds")),
    )

    # --- reject unsupported file type ---
    r = c.post(
        f"/api/v1/meetings/{mid}/audio",
        headers=h,
        files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    check("reject bad file type", r.status_code == 400, f"status={r.status_code}")

    # --- get meeting ---
    r = c.get(f"/api/v1/meetings/{mid}", headers=h)
    check("get meeting", r.status_code == 200 and r.json()["title"] == "Sprint Planning", "")

    # --- audio streaming (via ?token=, for <audio> tags) ---
    r = c.get(f"/api/v1/meetings/{mid}/audio?token={token}")
    check(
        "stream audio with token",
        r.status_code == 200 and r.content.startswith(b"RIFF"),
        f"status={r.status_code}",
    )

    # --- audio streaming rejects missing/invalid token ---
    r = c.get(f"/api/v1/meetings/{mid}/audio")
    check("audio without token rejected", r.status_code == 401, f"status={r.status_code}")
    r = c.get(f"/api/v1/meetings/{mid}/audio?token=not-a-real-token")
    check("audio with bad token rejected", r.status_code == 401, f"status={r.status_code}")

    # --- summary before processing is empty but valid ---
    r = c.get(f"/api/v1/meetings/{mid}/summary", headers=h)
    check("get summary (empty)", r.status_code == 200 and r.json()["decisions"] == [], "")

    # --- task CRUD ---
    r = c.post(
        "/api/v1/tasks",
        headers=h,
        json={"workspace_id": ws, "title": "Build login page", "priority": "high"},
    )
    tid = r.json().get("id", "")
    check("create task", r.status_code == 201 and tid, f"status={r.json().get('status')}")

    r = c.patch(
        f"/api/v1/tasks/{tid}",
        headers=h,
        json={"status": "in_progress", "actual_hours": 2.5},
    )
    check("update task", r.status_code == 200 and r.json()["status"] == "in_progress", "")

    r = c.patch(
        f"/api/v1/tasks/{tid}",
        headers=h,
        json={"status": "done"},
    )
    check(
        "complete task sets completed_at",
        r.status_code == 200 and r.json().get("completed_at") is not None,
        "",
    )

    r = c.get(f"/api/v1/workspaces/{ws}/tasks", headers=h)
    check("list tasks", r.status_code == 200 and len(r.json()) == 1, f"count={len(r.json())}")

    # --- meeting task list endpoint ---
    r = c.get(f"/api/v1/meetings/{mid}/tasks", headers=h)
    check("list meeting tasks", r.status_code == 200, f"count={len(r.json())}")

    # --- member guard: second user cannot access workspace ---
    email2 = f"other+{uuid.uuid4().hex[:6]}@example.com"
    r = c.post(
        "/api/v1/auth/register",
        json={"email": email2, "password": "secret123", "name": "Other"},
    )
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = c.get(f"/api/v1/workspaces/{ws}/tasks", headers=h2)
    check("non-member blocked", r.status_code == 403, f"status={r.status_code}")

    token2 = c.post(
        "/api/v1/auth/login", json={"email": email2, "password": "secret123"}
    ).json()["access_token"]
    r = c.get(f"/api/v1/meetings/{mid}/audio?token={token2}")
    check("audio blocked for non-member", r.status_code == 403, f"status={r.status_code}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    code = run()
    # cleanup throwaway db
    try:
        os.remove(TEST_DB)
    except OSError:
        pass
    sys.exit(code)
