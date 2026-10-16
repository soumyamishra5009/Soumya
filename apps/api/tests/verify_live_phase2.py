"""Live Phase 2 verification against a running API (real HTTP, no TestClient).

Covers team execution: members, assignees, task filters, editable AI output,
decision CRUD and meeting archive — all over real HTTP.

Usage (from apps/api):  python tests/verify_live_phase2.py [base_url]
"""

from __future__ import annotations

import sys
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


def register(c: httpx.Client, name: str) -> tuple[str, dict]:
    email = f"p2+{name.lower()}+{uuid.uuid4().hex[:6]}@example.com"
    r = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": name},
    )
    r.raise_for_status()
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=15.0) as c:
        owner_email, owner_h = register(c, "Owner")
        mate_email, mate_h = register(c, "Mate")

        r = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Phase2 WS"})
        ws = r.json()["id"]
        check("create workspace", r.status_code == 201, r.json().get("slug", ""))

        r = c.get(f"/api/v1/workspaces/{ws}/members", headers=owner_h)
        check(
            "members: owner listed",
            r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["is_owner"],
            f"n={len(r.json()) if r.status_code == 200 else '?'}",
        )

        r = c.post(
            f"/api/v1/workspaces/{ws}/members",
            headers=owner_h,
            json={"email": mate_email, "role": "member"},
        )
        mate_id = r.json().get("user_id") if r.status_code == 201 else ""
        check("members: add by email", r.status_code == 201, f"status={r.status_code}")

        r = c.post(
            "/api/v1/tasks",
            headers=owner_h,
            json={"workspace_id": ws, "title": "Assigned task", "assignee_id": mate_id},
        )
        check(
            "assign: member assignee",
            r.status_code == 201 and r.json()["assignee_id"] == mate_id,
            f"status={r.status_code}",
        )

        r = c.get(f"/api/v1/workspaces/{ws}/tasks?assignee_id=me", headers=mate_h)
        check(
            "filters: assignee=me",
            r.status_code == 200 and len(r.json()) == 1,
            f"n={len(r.json()) if r.status_code == 200 else '?'}",
        )

        r = c.get(f"/api/v1/workspaces/{ws}/tasks?q=assigned", headers=owner_h)
        check("filters: search", r.status_code == 200 and len(r.json()) == 1, "")

        r = c.post(
            "/api/v1/meetings",
            headers=owner_h,
            json={"workspace_id": ws, "title": "Phase2 meeting", "consent_confirmed": True},
        )
        mid = r.json()["id"]
        check("create meeting", r.status_code == 201, "")

        r = c.patch(
            f"/api/v1/meetings/{mid}",
            headers=owner_h,
            json={"summary": "Edited by a human.", "key_points": ["KP1"]},
        )
        check(
            "meeting: edit AI output",
            r.status_code == 200 and r.json()["summary"] == "Edited by a human.",
            f"status={r.status_code}",
        )

        r = c.post(
            f"/api/v1/meetings/{mid}/decisions",
            headers=owner_h,
            json={"title": "Use SQLite for dev", "impact": "low"},
        )
        did = r.json().get("id") if r.status_code == 201 else ""
        check("decision: create", r.status_code == 201, f"status={r.status_code}")

        r = c.patch(
            f"/api/v1/decisions/{did}", headers=owner_h, json={"impact": "high"}
        )
        check(
            "decision: patch",
            r.status_code == 200 and r.json()["impact"] == "high",
            f"status={r.status_code}",
        )

        r = c.get(f"/api/v1/meetings/{mid}/summary", headers=owner_h)
        check(
            "summary: includes decision",
            r.status_code == 200 and len(r.json()["decisions"]) == 1,
            f"n={len(r.json()['decisions']) if r.status_code == 200 else '?'}",
        )

        r = c.patch(f"/api/v1/meetings/{mid}", headers=owner_h, json={"archived": True})
        check("meeting: archive", r.status_code == 200 and r.json()["archived"] is True, "")

        r = c.get(f"/api/v1/workspaces/{ws}/meetings", headers=owner_h)
        check("meetings: active list excludes archived", len(r.json()) == 0, f"n={len(r.json())}")

        r = c.get(f"/api/v1/workspaces/{ws}/meetings?archived=true", headers=owner_h)
        check("meetings: archive list", len(r.json()) == 1, f"n={len(r.json())}")

        r = c.delete(f"/api/v1/decisions/{did}", headers=owner_h)
        check("decision: delete", r.status_code == 204, f"status={r.status_code}")

        r = c.delete(f"/api/v1/workspaces/{ws}/members/{mate_id}", headers=owner_h)
        check("members: remove", r.status_code == 204, f"status={r.status_code}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
