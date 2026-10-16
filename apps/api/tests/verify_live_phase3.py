"""Live Phase 3 verification against a running API (real HTTP, no TestClient).

Covers the Dev Studio over real HTTP: sandbox file tree, create/read/write/
delete, path-escape refusal, offline lint, context-aware chat, and the
human-in-the-loop change proposals (create → review → approve/reject).

Usage (from apps/api):  python tests/verify_live_phase3.py [base_url]
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
    email = f"p3+{name.lower()}+{uuid.uuid4().hex[:6]}@example.com"
    r = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": name},
    )
    r.raise_for_status()
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as c:
        owner_h = register(c, "StudioOwner")[1]
        stray_h = register(c, "StudioStray")[1]

        r = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Phase3 Studio WS"})
        check("create workspace", r.status_code == 201, r.json().get("slug", ""))
        ws = r.json()["id"]
        base = f"/api/v1/workspaces/{ws}/studio"

        # --------------------------------------------------------------- tree
        r = c.get(f"{base}/tree", headers=owner_h)
        check(
            "studio: empty tree",
            r.status_code == 200 and r.json()["empty"] is True,
            f"status={r.status_code}",
        )

        r = c.post(f"{base}/seed", headers=owner_h)
        check(
            "studio: sample project seeded",
            r.status_code == 201 and len(r.json()["created"]) == 4,
            f"created={len(r.json().get('created', [])) if r.status_code == 201 else r.status_code}",
        )

        r = c.get(f"{base}/tree", headers=owner_h)
        paths = []

        def walk(node):
            if node.get("type") == "file":
                paths.append(node["path"])
            for child in node.get("children") or []:
                walk(child)

        if r.status_code == 200:
            walk(r.json())
        check(
            "studio: tree lists sample files",
            "src/calculator.py" in paths and "tests/test_calculator.py" in paths,
            f"n={len(paths)}",
        )

        # -------------------------------------------------------------- files
        r = c.get(f"{base}/files/src/calculator.py", headers=owner_h)
        check(
            "studio: read file",
            r.status_code == 200 and r.json()["language"] == "python",
            f"status={r.status_code}",
        )

        r = c.put(
            f"{base}/files/src/scratch.py",
            headers=owner_h,
            json={"content": "value = 1\n"},
        )
        check("studio: write file", r.status_code == 200, f"status={r.status_code}")

        r = c.get(f"{base}/files/%2e%2e%2f%2e%2e%2fescape.txt", headers=owner_h)
        check("studio: path escape refused", r.status_code == 400, f"status={r.status_code}")

        r = c.post(f"{base}/files", headers=owner_h, json={"path": "docs", "kind": "dir"})
        check("studio: create directory", r.status_code == 201, f"status={r.status_code}")

        # --------------------------------------------------------------- lint
        r = c.post(
            f"{base}/lint?path=src/scratch.py",
            headers=owner_h,
            json={"content": "def f(a=[]):\n    return a == None\n"},
        )
        check(
            "studio: offline lint finds issues",
            r.status_code == 200 and len(r.json()["findings"]) >= 2,
            f"n={len(r.json()['findings']) if r.status_code == 200 else '?'}",
        )

        # --------------------------------------------------------------- chat
        r = c.post(
            f"{base}/chat",
            headers=owner_h,
            json={"message": "Explain this file", "file_path": "src/calculator.py"},
        )
        body = r.json() if r.status_code == 200 else {}
        check(
            "studio: chat answers",
            r.status_code == 200 and bool(body.get("answer")),
            f"status={r.status_code} source={body.get('source')}",
        )
        check(
            "studio: chat reports context",
            body.get("context_used", {}).get("file_path") == "src/calculator.py",
            str(body.get("context_used")),
        )

        # linked meeting + task context
        r = c.post(
            "/api/v1/meetings",
            headers=owner_h,
            json={"workspace_id": ws, "title": "Studio sync", "consent_confirmed": True},
        )
        mid = r.json()["id"]
        c.patch(f"/api/v1/meetings/{mid}", headers=owner_h, json={"summary": "Ship the dev studio."})
        r = c.post(
            "/api/v1/tasks",
            headers=owner_h,
            json={"workspace_id": ws, "title": "Fix divide bug", "priority": "high"},
        )
        tid = r.json()["id"]

        r = c.post(
            f"{base}/chat",
            headers=owner_h,
            json={"message": "what next?", "file_path": "src/calculator.py", "meeting_id": mid, "task_id": tid},
        )
        ctx = r.json().get("context_used", {}) if r.status_code == 200 else {}
        check(
            "studio: chat links meeting + task",
            ctx.get("meeting_linked") is True and ctx.get("task_linked") is True,
            str(ctx),
        )

        # ---------------------------------------------------------- proposals
        before = c.get(f"{base}/files/src/calculator.py", headers=owner_h).json()["content"]

        r = c.post(
            f"{base}/proposals",
            headers=owner_h,
            json={"file_path": "src/calculator.py", "instruction": "guard against division by zero"},
        )
        check(
            "studio: proposal created pending",
            r.status_code == 201 and r.json()["status"] == "pending",
            f"status={r.status_code}",
        )
        pid = r.json()["id"]
        proposed = r.json()["proposed_content"]

        after = c.get(f"{base}/files/src/calculator.py", headers=owner_h).json()["content"]
        check("studio: proposal does not write", before == after, "")

        r = c.post(f"{base}/proposals/{pid}/approve", headers=owner_h)
        check(
            "studio: approve applies change",
            r.status_code == 200 and r.json()["applied"] is True,
            f"status={r.status_code}",
        )

        after = c.get(f"{base}/files/src/calculator.py", headers=owner_h).json()["content"]
        check("studio: file matches approved proposal", after == proposed, "")

        r = c.post(f"{base}/proposals/{pid}/approve", headers=owner_h)
        check("studio: double approve refused", r.status_code == 409, f"status={r.status_code}")

        r = c.post(
            f"{base}/proposals",
            headers=owner_h,
            json={"file_path": "src/scratch.py", "instruction": "add a comment"},
        )
        pid2 = r.json()["id"]
        r = c.post(f"{base}/proposals/{pid2}/reject", headers=owner_h)
        check(
            "studio: reject leaves file alone",
            r.status_code == 200 and r.json()["applied"] is False,
            f"status={r.status_code}",
        )

        r = c.get(f"{base}/proposals?status=approved", headers=owner_h)
        check(
            "studio: proposals filter by status",
            r.status_code == 200 and len(r.json()) == 1,
            f"n={len(r.json()) if r.status_code == 200 else '?'}",
        )

        # ------------------------------------------------------------ cleanup
        r = c.delete(f"{base}/files/src/scratch.py", headers=owner_h)
        check("studio: delete file", r.status_code == 200, f"status={r.status_code}")

        # -------------------------------------------------------- permissions
        r = c.get(f"{base}/tree", headers=stray_h)
        check("studio: non-member blocked", r.status_code == 403, f"status={r.status_code}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
