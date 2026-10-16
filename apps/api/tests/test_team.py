"""Phase 2 team-execution tests: editable AI output, members, task filters.

Run from apps/api:  python tests/test_team.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = os.path.join(tempfile.gettempdir(), f"test_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.replace(os.sep, '/')}"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


def register(c: TestClient, name: str) -> tuple[str, dict]:
    email = f"{name.lower()}+{uuid.uuid4().hex[:6]}@example.com"
    r = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": name},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def run() -> int:
    from app.core.database import init_db

    init_db()
    c = TestClient(main.app)

    owner_email, owner_h = register(c, "Owner")
    mate_email, mate_h = register(c, "Mate")
    stray_email, stray_h = register(c, "Stray")

    # --- workspace owned by "Owner" ---
    ws = c.post(
        "/api/v1/workspaces", headers=owner_h, json={"name": "Team WS"}
    ).json()["id"]

    # ---------------------------------------------------------------- members
    r = c.get(f"/api/v1/workspaces/{ws}/members", headers=owner_h)
    body = r.json() if r.status_code == 200 else []
    check(
        "members: owner auto-listed",
        r.status_code == 200 and len(body) == 1 and body[0]["is_owner"],
        f"count={len(body)}",
    )

    r = c.post(
        f"/api/v1/workspaces/{ws}/members",
        headers=owner_h,
        json={"email": "nobody@nowhere.test", "role": "member"},
    )
    check("members: unknown email rejected", r.status_code == 404, f"status={r.status_code}")

    r = c.post(
        f"/api/v1/workspaces/{ws}/members",
        headers=owner_h,
        json={"email": mate_email, "role": "member"},
    )
    mate_id = r.json().get("user_id", "") if r.status_code == 201 else ""
    check(
        "members: add existing account",
        r.status_code == 201 and mate_id and r.json().get("name") == "Mate",
        f"status={r.status_code}",
    )

    r = c.post(
        f"/api/v1/workspaces/{ws}/members",
        headers=owner_h,
        json={"email": mate_email, "role": "member"},
    )
    check("members: duplicate rejected", r.status_code == 409, f"status={r.status_code}")

    r = c.post(
        f"/api/v1/workspaces/{ws}/members",
        headers=owner_h,
        json={"email": owner_email, "role": "member"},
    )
    check("members: owner cannot be re-added", r.status_code == 409, f"status={r.status_code}")

    r = c.get(f"/api/v1/workspaces/{ws}/members", headers=owner_h)
    check("members: list has 2", len(r.json()) == 2, f"count={len(r.json())}")

    # a plain member cannot invite others
    r = c.post(
        f"/api/v1/workspaces/{ws}/members",
        headers=mate_h,
        json={"email": stray_email, "role": "member"},
    )
    check("members: non-manager cannot invite", r.status_code == 403, f"status={r.status_code}")

    # member can now see the workspace
    r = c.get(f"/api/v1/workspaces/{ws}/tasks", headers=mate_h)
    check("members: new member gains access", r.status_code == 200, f"status={r.status_code}")

    # ---------------------------------------------------------- assignment
    r = c.post(
        "/api/v1/tasks",
        headers=owner_h,
        json={"workspace_id": ws, "title": "Ship login", "assignee_id": mate_id},
    )
    check(
        "assign: member assignee accepted",
        r.status_code == 201 and r.json().get("assignee_id") == mate_id,
        f"status={r.status_code}",
    )

    stray_id = c.get("/api/v1/auth/me", headers=stray_h).json()["id"]
    r = c.post(
        "/api/v1/tasks",
        headers=owner_h,
        json={"workspace_id": ws, "title": "Nope", "assignee_id": stray_id},
    )
    check("assign: non-member rejected", r.status_code == 400, f"status={r.status_code}")

    r = c.post(
        "/api/v1/tasks",
        headers=owner_h,
        json={"workspace_id": ws, "title": "Ghost", "assignee_id": "does-not-exist"},
    )
    check("assign: unknown user rejected", r.status_code == 404, f"status={r.status_code}")

    # ------------------------------------------------------------ task filters
    c.post(
        "/api/v1/tasks",
        headers=owner_h,
        json={"workspace_id": ws, "title": "Urgent migration", "priority": "urgent"},
    )
    c.post(
        "/api/v1/tasks",
        headers=owner_h,
        json={
            "workspace_id": ws,
            "title": "Write docs",
            "priority": "low",
            "due_date": "2026-01-15T00:00:00Z",
        },
    )

    def titles(resp) -> set[str]:
        return {t["title"] for t in resp.json()}

    r = c.get(f"/api/v1/workspaces/{ws}/tasks", headers=owner_h)
    check("filters: unfiltered returns all", len(r.json()) == 3, f"count={len(r.json())}")

    r = c.get(f"/api/v1/workspaces/{ws}/tasks?assignee_id=me", headers=owner_h)
    check("filters: assignee=me (owner has none)", len(r.json()) == 0, f"count={len(r.json())}")

    r = c.get(f"/api/v1/workspaces/{ws}/tasks?assignee_id=me", headers=mate_h)
    check("filters: assignee=me (mate has one)", titles(r) == {"Ship login"}, str(titles(r)))

    r = c.get(f"/api/v1/workspaces/{ws}/tasks?assignee_id=unassigned", headers=owner_h)
    check("filters: unassigned", len(r.json()) == 2, f"count={len(r.json())}")

    r = c.get(f"/api/v1/workspaces/{ws}/tasks?priority=urgent", headers=owner_h)
    check("filters: priority", titles(r) == {"Urgent migration"}, str(titles(r)))

    r = c.get(f"/api/v1/workspaces/{ws}/tasks?q=log", headers=owner_h)
    check("filters: search", titles(r) == {"Ship login"}, str(titles(r)))

    r = c.get(
        f"/api/v1/workspaces/{ws}/tasks?due_before=2026-02-01T00:00:00Z", headers=owner_h
    )
    check("filters: due_before", titles(r) == {"Write docs"}, str(titles(r)))

    r = c.get(
        f"/api/v1/workspaces/{ws}/tasks?due_after=2026-02-01T00:00:00Z", headers=owner_h
    )
    check("filters: due_after excludes dated-before", "Write docs" not in titles(r), str(titles(r)))

    # ------------------------------------------------------ editable AI output
    mid = c.post(
        "/api/v1/meetings",
        headers=owner_h,
        json={"workspace_id": ws, "title": "Kickoff", "consent_confirmed": True},
    ).json()["id"]

    r = c.patch(
        f"/api/v1/meetings/{mid}",
        headers=owner_h,
        json={"summary": "Human-edited summary.", "key_points": ["A", "B"]},
    )
    check(
        "meeting: patch summary",
        r.status_code == 200 and r.json()["summary"] == "Human-edited summary.",
        f"status={r.status_code}",
    )
    check("meeting: patch key_points", r.json()["key_points"] == ["A", "B"], str(r.json()["key_points"]))

    r = c.patch(f"/api/v1/meetings/{mid}", headers=owner_h, json={"title": "Kickoff v2"})
    check(
        "meeting: partial patch keeps other fields",
        r.json()["title"] == "Kickoff v2" and r.json()["summary"] == "Human-edited summary.",
        "",
    )

    # --------------------------------------------------------- decision CRUD
    r = c.post(
        f"/api/v1/meetings/{mid}/decisions",
        headers=owner_h,
        json={"title": "Adopt Postgres", "impact": "high", "rationale": "scale"},
    )
    did = r.json().get("id", "") if r.status_code == 201 else ""
    check("decision: manual create", r.status_code == 201 and did, f"status={r.status_code}")

    r = c.patch(f"/api/v1/decisions/{did}", headers=owner_h, json={"title": "Adopt Postgres 16"})
    check(
        "decision: patch title",
        r.status_code == 200 and r.json()["title"] == "Adopt Postgres 16",
        f"status={r.status_code}",
    )

    r = c.patch(f"/api/v1/decisions/{did}", headers=owner_h, json={"impact": "nonsense"})
    check("decision: invalid impact rejected", r.status_code == 422, f"status={r.status_code}")

    r = c.get(f"/api/v1/meetings/{mid}/summary", headers=owner_h)
    check(
        "decision: appears in summary",
        any(d["title"] == "Adopt Postgres 16" for d in r.json()["decisions"]),
        f"n={len(r.json()['decisions'])}",
    )

    # a non-member cannot edit
    r = c.patch(f"/api/v1/decisions/{did}", headers=stray_h, json={"title": "Hijack"})
    check("decision: non-member blocked", r.status_code == 403, f"status={r.status_code}")

    r = c.delete(f"/api/v1/decisions/{did}", headers=owner_h)
    check("decision: delete", r.status_code == 204, f"status={r.status_code}")

    r = c.delete(f"/api/v1/decisions/{did}", headers=owner_h)
    check("decision: delete twice -> 404", r.status_code == 404, f"status={r.status_code}")

    # -------------------------------------------------- meeting list + archive
    mid2 = c.post(
        "/api/v1/meetings",
        headers=owner_h,
        json={"workspace_id": ws, "title": "Retro", "consent_confirmed": True},
    ).json()["id"]

    r = c.get(f"/api/v1/workspaces/{ws}/meetings", headers=owner_h)
    check("meetings: list active", r.status_code == 200 and len(r.json()) == 2, f"count={len(r.json())}")

    r = c.get(f"/api/v1/workspaces/{ws}/meetings?q=retro", headers=owner_h)
    check("meetings: search", [m["id"] for m in r.json()] == [mid2], f"count={len(r.json())}")

    r = c.patch(f"/api/v1/meetings/{mid2}", headers=owner_h, json={"archived": True})
    check("meetings: archive flag set", r.status_code == 200 and r.json()["archived"] is True, "")

    r = c.get(f"/api/v1/workspaces/{ws}/meetings", headers=owner_h)
    check("meetings: archived hidden by default", len(r.json()) == 1, f"count={len(r.json())}")

    r = c.get(f"/api/v1/workspaces/{ws}/meetings?archived=true", headers=owner_h)
    check("meetings: archive view", [m["id"] for m in r.json()] == [mid2], f"count={len(r.json())}")

    # -------------------------------------------------------- remove member
    r = c.delete(f"/api/v1/workspaces/{ws}/members/{mate_id}", headers=owner_h)
    check("members: remove", r.status_code == 204, f"status={r.status_code}")

    r = c.get(f"/api/v1/workspaces/{ws}/tasks", headers=mate_h)
    check("members: removed member loses access", r.status_code == 403, f"status={r.status_code}")

    owner_id = c.get("/api/v1/auth/me", headers=owner_h).json()["id"]
    r = c.delete(f"/api/v1/workspaces/{ws}/members/{owner_id}", headers=owner_h)
    check("members: owner cannot be removed", r.status_code == 400, f"status={r.status_code}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    code = run()
    try:
        os.remove(TEST_DB)
    except OSError:
        pass
    sys.exit(code)
