"""Live Phase 4 verification against a running API (real HTTP, no TestClient).

Covers the "ship it" pipeline over real HTTP: repository connections, the local
git provider, pull-request proposals (draft → open → merge/close) and the
Meeting→Code agent (plan → apply → pending proposals).

Usage (from apps/api):  python tests/verify_live_phase4.py [base_url]
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
    email = f"p4+{name.lower()}+{uuid.uuid4().hex[:6]}@example.com"
    r = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": name},
    )
    r.raise_for_status()
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as c:
        owner_h = register(c, "ShipOwner")[1]
        stray_h = register(c, "ShipStray")[1]

        r = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Phase4 Ship WS"})
        check("create workspace", r.status_code == 201, r.json().get("slug", ""))
        ws = r.json()["id"]

        studio = f"/api/v1/workspaces/{ws}/studio"
        git = f"/api/v1/workspaces/{ws}/git"
        repos = f"/api/v1/workspaces/{ws}/repos"
        prs = f"/api/v1/workspaces/{ws}/pull-requests"
        agent = f"/api/v1/workspaces/{ws}/agent"

        # ---------------------------------------------------------- repo + git
        r = c.post(repos, headers=owner_h, json={"provider": "local"})
        check(
            "repos: connect local sandbox",
            r.status_code == 201 and r.json()["provider"] == "local",
            f"status={r.status_code}",
        )
        local_repo = r.json()["id"]

        r = c.post(f"{repos}/{local_repo}/check", headers=owner_h)
        check(
            "repos: local check ok",
            r.status_code == 200 and r.json()["ok"] is True,
            r.json().get("message", ""),
        )

        r = c.post(f"{studio}/seed", headers=owner_h)
        check("studio: sample project seeded", r.status_code == 201, "")

        r = c.get(f"{git}/status", headers=owner_h)
        body = r.json()
        check(
            "git: initialises a clean baseline",
            r.status_code == 200 and body["initialized"] is True and body["clean"] is True,
            f"branch={body.get('branch')}",
        )

        r = c.get(f"{git}/log", headers=owner_h)
        check("git: baseline commit", r.status_code == 200 and len(r.json()) >= 1, f"n={len(r.json())}")

        # ---------------------------------------------------- approve → ship PR
        r = c.post(
            f"{studio}/proposals",
            headers=owner_h,
            json={"file_path": "src/calculator.py", "instruction": "guard against division by zero"},
        )
        check("studio: proposal created", r.status_code == 201, f"status={r.status_code}")
        pid = r.json()["id"]

        r = c.post(f"{studio}/proposals/{pid}/approve", headers=owner_h)
        check(
            "studio: proposal approved (written)",
            r.status_code == 200 and r.json()["applied"] is True,
            f"status={r.status_code}",
        )

        r = c.get(f"{git}/status", headers=owner_h)
        check(
            "git: approved change is dirty",
            r.status_code == 200 and r.json()["clean"] is False,
            f"changed={len(r.json().get('changed_files', []))}",
        )

        r = c.post(
            prs,
            headers=owner_h,
            json={"title": "Guard divide by zero", "proposal_ids": [pid]},
        )
        check(
            "pr: draft created",
            r.status_code == 201 and r.json()["status"] == "draft",
            f"status={r.status_code} files={r.json().get('file_count') if r.status_code == 201 else '?'}",
        )
        pr_id = r.json()["id"]

        r = c.post(f"{prs}/{pr_id}/open", headers=owner_h)
        check(
            "pr: opened (real commit)",
            r.status_code == 200
            and r.json()["proposal"]["status"] == "open"
            and bool(r.json()["proposal"]["commit_sha"]),
            r.json().get("message", ""),
        )

        r = c.get(f"{git}/status", headers=owner_h)
        check(
            "git: on the feature branch",
            r.json()["branch"].startswith("syncforge/"),
            f"branch={r.json().get('branch')}",
        )

        r = c.post(f"{prs}/{pr_id}/merge", headers=owner_h)
        check(
            "pr: merged into base",
            r.status_code == 200 and r.json()["proposal"]["status"] == "merged",
            f"status={r.status_code}",
        )

        r = c.get(f"{git}/status", headers=owner_h)
        check(
            "git: back on main after merge",
            r.json()["branch"] == "main" and r.json()["clean"] is True,
            f"branch={r.json().get('branch')}",
        )

        # --------------------------------------------------------- close a draft
        r = c.post(
            f"{studio}/proposals",
            headers=owner_h,
            json={"file_path": "src/calculator.py", "instruction": "add a docstring"},
        )
        c.post(f"{studio}/proposals/{r.json()['id']}/approve", headers=owner_h)
        r = c.post(prs, headers=owner_h, json={"title": "Close me"})
        close_id = r.json()["id"]
        r = c.post(f"{prs}/{close_id}/close", headers=owner_h)
        check(
            "pr: draft closed",
            r.status_code == 200 and r.json()["proposal"]["status"] == "closed",
            f"status={r.status_code}",
        )

        r = c.get(f"{prs}?status=merged", headers=owner_h)
        check(
            "pr: filter by status",
            r.status_code == 200 and len(r.json()) == 1,
            f"n={len(r.json()) if r.status_code == 200 else '?'}",
        )

        # -------------------------------------------------------- github (no token)
        r = c.post(
            repos,
            headers=owner_h,
            json={"provider": "github", "repo_full_name": "syncforge/demo"},
        )
        check("repos: github metadata connect", r.status_code == 201, f"status={r.status_code}")
        gh_id = r.json()["id"]
        r = c.post(f"{repos}/{gh_id}/check", headers=owner_h)
        check(
            "repos: github check reports missing token",
            r.status_code == 200 and r.json()["ok"] is False
            and "GITHUB_TOKEN" in r.json()["message"],
            r.json().get("message", ""),
        )

        # ------------------------------------------------------------- the agent
        r = c.post(
            "/api/v1/meetings",
            headers=owner_h,
            json={"workspace_id": ws, "title": "Architecture sync", "consent_confirmed": True},
        )
        mid = r.json()["id"]
        c.patch(
            f"/api/v1/meetings/{mid}",
            headers=owner_h,
            json={"summary": "We agreed to guard the divide-by-zero path in the calculator."},
        )
        c.post(
            f"/api/v1/meetings/{mid}/decisions",
            headers=owner_h,
            json={
                "title": "Guard divide by zero",
                "description": "divide() must return None when the divisor is zero",
                "impact": "high",
            },
        )
        c.post(
            "/api/v1/tasks",
            headers=owner_h,
            json={"workspace_id": ws, "title": "Fix divide bug", "priority": "high", "meeting_id": mid},
        )

        r = c.post(f"{agent}/plan", headers=owner_h, json={"meeting_id": mid})
        plan = r.json()
        check(
            "agent: plan generated",
            r.status_code == 201 and bool(plan.get("title")),
            f"status={r.status_code} source={plan.get('source')}",
        )
        paths = [f["path"] for f in plan.get("affected_files", [])]
        check(
            "agent: locates the affected file",
            "src/calculator.py" in paths,
            str(paths),
        )
        check(
            "agent: proposals target that file",
            bool(plan.get("proposed_changes"))
            and plan["proposed_changes"][0]["path"] == "src/calculator.py",
            str(plan.get("proposed_changes"))[:100],
        )

        r = c.post(f"{agent}/plans/{plan['id']}/apply", headers=owner_h)
        applied = r.json()
        check(
            "agent: apply creates pending proposals",
            r.status_code == 200 and applied.get("created", 0) >= 1,
            f"status={r.status_code} created={applied.get('created')}",
        )

        r = c.get(f"{studio}/proposals?status=pending", headers=owner_h)
        check(
            "agent: proposals are pending (unwritten)",
            r.status_code == 200 and len(r.json()) >= 1,
            f"pending={len(r.json()) if r.status_code == 200 else '?'}",
        )

        r = c.post(f"{agent}/plans/{plan['id']}/apply", headers=owner_h)
        check("agent: cannot apply twice", r.status_code == 409, f"status={r.status_code}")

        # ---------------------------------------------------------- permissions
        r = c.get(f"{git}/status", headers=stray_h)
        check("ship: non-member blocked", r.status_code == 403, f"status={r.status_code}")

        # -------------------------------------------------------------- cleanup
        r = c.delete(f"{repos}/{gh_id}", headers=owner_h)
        check("repos: disconnect", r.status_code == 204, f"status={r.status_code}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
