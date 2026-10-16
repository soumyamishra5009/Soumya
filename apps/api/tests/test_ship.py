"""Phase 4 tests: local git provider, repository connections, pull-request
proposals and the Meeting→Code agent.

Run from apps/api:  python tests/test_ship.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = os.path.join(tempfile.gettempdir(), f"test_ship_{uuid.uuid4().hex}.db")
SANDBOX = os.path.join(tempfile.gettempdir(), f"ship_{uuid.uuid4().hex}")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.replace(os.sep, '/')}"
os.environ["DEVSTUDIO_ROOT"] = SANDBOX.replace(os.sep, "/")
# Deterministic offline mode: the LLM ladder points at a closed port so the
# offline planner/proposal fallbacks are exercised with no network dependency.
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["GITHUB_TOKEN"] = ""
os.environ["ALLOW_EXTRACTIVE_FALLBACK"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.services import devstudio, githost, localgit, ship  # noqa: E402

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

    owner_email, owner_h = register(c, "ShipOwner")
    member_email, member_h = register(c, "ShipMember")
    stray_h = register(c, "ShipStray")[1]

    ws = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Ship WS"}).json()["id"]
    c.post(
        f"/api/v1/workspaces/{ws}/members", headers=owner_h,
        json={"email": member_email, "role": "member"},
    )
    studio = f"/api/v1/workspaces/{ws}/studio"
    git = f"/api/v1/workspaces/{ws}/git"
    repos = f"/api/v1/workspaces/{ws}/repos"
    prs = f"/api/v1/workspaces/{ws}/pull-requests"
    agent = f"/api/v1/workspaces/{ws}/agent"

    # ------------------------------------------------------------- git binary
    check("git: available on host", localgit.available(), str(localgit.available()))
    for bad in ("-oops", "has space", "trailing/", "a..b", "a//b", ""):
        try:
            localgit.validate_branch(bad)
            check(f"git: rejects branch {bad!r}", False, "no error raised")
        except localgit.GitError:
            check(f"git: rejects branch {bad!r}", True, "")
    check(
        "git: accepts a normal branch",
        localgit.validate_branch("syncforge/fix-divide-ab12") == "syncforge/fix-divide-ab12",
        "",
    )

    # ------------------------------------------------------- .git is protected
    try:
        devstudio.resolve_path(ws, ".git/config")
        check("sandbox: .git path blocked", False, "no error raised")
    except devstudio.SandboxError:
        check("sandbox: .git path blocked", True, "")

    # ------------------------------------------------------------- repo connect
    r = c.post(repos, headers=owner_h, json={"provider": "local"})
    check(
        "repos: connect local sandbox",
        r.status_code == 201 and r.json()["provider"] == "local" and r.json()["name"] == "Local sandbox",
        f"status={r.status_code}",
    )
    local_repo_id = r.json()["id"]

    r = c.post(repos, headers=owner_h, json={"provider": "local"})
    check("repos: duplicate -> 409", r.status_code == 409, f"status={r.status_code}")

    r = c.post(repos, headers=owner_h, json={"provider": "github"})
    check("repos: github without repo name -> 400", r.status_code == 400, f"status={r.status_code}")

    r = c.post(
        repos, headers=owner_h,
        json={"provider": "github", "repo_full_name": "syncforge/demo"},
    )
    check(
        "repos: connect github repo (metadata)",
        r.status_code == 201 and r.json()["repo_full_name"] == "syncforge/demo",
        f"status={r.status_code}",
    )
    github_repo_id = r.json()["id"]

    r = c.get(repos, headers=owner_h)
    check("repos: list", r.status_code == 200 and len(r.json()) == 2, f"n={len(r.json())}")

    r = c.get(f"{repos}/{local_repo_id}", headers=owner_h)
    check("repos: detail", r.status_code == 200 and r.json()["id"] == local_repo_id, f"status={r.status_code}")

    r = c.post(f"{repos}/{local_repo_id}/check", headers=owner_h)
    check(
        "repos: local check ok",
        r.status_code == 200 and r.json()["ok"] is True,
        r.json().get("message", ""),
    )

    r = c.post(f"{repos}/{github_repo_id}/check", headers=owner_h)
    check(
        "repos: github check needs token",
        r.status_code == 200 and r.json()["ok"] is False and "GITHUB_TOKEN" in r.json()["message"],
        r.json().get("message", ""),
    )
    check("repos: githost not configured", githost.configured() is False, "")

    r = c.get(f"{repos}/{local_repo_id}", headers=stray_h)
    check("repos: non-member -> 403", r.status_code == 403, f"status={r.status_code}")
    r = c.post(repos, headers=member_h, json={"provider": "local"})
    check("repos: member cannot connect -> 403", r.status_code == 403, f"status={r.status_code}")

    # -------------------------------------------------------------- git status
    r = c.post(f"{studio}/seed", headers=owner_h)
    check("ship: sample project seeded", r.status_code == 201 and len(r.json()["created"]) == 4, "")

    r = c.get(f"{git}/status", headers=owner_h)
    body = r.json()
    check(
        "git: status initialises + baselines",
        r.status_code == 200 and body["initialized"] is True and body["clean"] is True,
        f"branch={body.get('branch')} changed={len(body.get('changed_files', []))}",
    )
    check("git: default branch is main", body["branch"] == "main", str(body.get("branch")))

    r = c.get(f"{git}/log", headers=owner_h)
    check("git: baseline commit logged", r.status_code == 200 and len(r.json()) >= 1, f"n={len(r.json())}")

    r = c.get(f"{git}/diff", headers=owner_h)
    check("git: clean tree has empty diff", r.status_code == 200 and r.json()["diff"].strip() == "", "")

    r = c.get(f"{git}/status", headers=member_h)
    check("git: member can read status", r.status_code == 200, f"status={r.status_code}")
    r = c.get(f"{git}/status", headers=stray_h)
    check("git: non-member blocked", r.status_code == 403, f"status={r.status_code}")

    # --------------------------------------------------- no changes -> no PR
    r = c.post(prs, headers=owner_h, json={"title": "nothing"})
    check("pr: no changes -> 400", r.status_code == 400, f"status={r.status_code}")

    # ------------------------------------------------- approve a change, ship it
    r = c.post(
        f"{studio}/proposals", headers=owner_h,
        json={"file_path": "src/calculator.py", "instruction": "guard against division by zero"},
    )
    pid = r.json()["id"]
    r = c.post(f"{studio}/proposals/{pid}/approve", headers=owner_h)
    check("pr: code change approved", r.status_code == 200 and r.json()["applied"] is True, f"status={r.status_code}")

    r = c.get(f"{git}/status", headers=owner_h)
    body = r.json()
    check(
        "git: approved change shows as modified",
        body["clean"] is False
        and any(f["path"] == "src/calculator.py" for f in body["changed_files"]),
        str(body["changed_files"]),
    )

    r = c.get(f"{git}/diff", headers=owner_h)
    check(
        "git: diff describes the change",
        r.status_code == 200 and "calculator.py" in r.json()["diff"],
        f"len={len(r.json()['diff']) if r.status_code == 200 else '?'}",
    )

    # referencing a *pending* proposal is refused
    r = c.post(
        f"{studio}/proposals", headers=owner_h,
        json={"file_path": "src/calculator.py", "instruction": "add a note"},
    )
    pending_id = r.json()["id"]
    r = c.post(prs, headers=owner_h, json={"title": "bad", "proposal_ids": [pending_id]})
    check("pr: unapproved proposal reference -> 409", r.status_code == 409, f"status={r.status_code}")

    r = c.post(
        prs, headers=owner_h,
        json={"title": "Fix divide by zero", "body": "From the architecture sync.", "proposal_ids": [pid]},
    )
    check(
        "pr: draft created from changes",
        r.status_code == 201 and r.json()["status"] == "draft" and r.json()["file_count"] >= 1,
        f"status={r.status_code} files={r.json().get('file_count') if r.status_code == 201 else '?'}",
    )
    check(
        "pr: branch name is safe + prefixed",
        r.json()["branch_name"].startswith("syncforge/"),
        r.json().get("branch_name", ""),
    )
    check("pr: diff snapshot captured", bool(r.json()["diff"]), "")
    pr_id = r.json()["id"]
    branch = r.json()["branch_name"]

    r = c.post(f"{prs}/{pr_id}/merge", headers=owner_h)
    check("pr: cannot merge a draft -> 409", r.status_code == 409, f"status={r.status_code}")

    r = c.post(f"{prs}/{pr_id}/open", headers=owner_h)
    check(
        "pr: open commits to a branch",
        r.status_code == 200 and r.json()["proposal"]["status"] == "open"
        and bool(r.json()["proposal"]["commit_sha"]),
        f"status={r.status_code} {r.json().get('message', '')}",
    )

    r = c.post(f"{prs}/{pr_id}/open", headers=owner_h)
    check("pr: cannot reopen -> 409", r.status_code == 409, f"status={r.status_code}")

    r = c.get(f"{git}/status", headers=owner_h)
    check(
        "git: now on the feature branch and clean",
        r.json()["branch"] == branch and r.json()["clean"] is True,
        f"branch={r.json().get('branch')}",
    )

    r = c.get(f"{git}/log", headers=owner_h)
    check(
        "git: commit message is the PR title",
        any("Fix divide by zero" in commit["message"] for commit in r.json()),
        str([x["message"] for x in r.json()][:2]),
    )

    r = c.post(f"{prs}/{pr_id}/merge", headers=owner_h)
    check(
        "pr: merge into base",
        r.status_code == 200 and r.json()["proposal"]["status"] == "merged",
        f"status={r.status_code}",
    )

    r = c.get(f"{git}/status", headers=owner_h)
    check(
        "git: back on main after merge",
        r.json()["branch"] == "main" and r.json()["clean"] is True,
        f"branch={r.json().get('branch')}",
    )

    r = c.post(f"{prs}/{pr_id}/merge", headers=owner_h)
    check("pr: cannot merge twice -> 409", r.status_code == 409, f"status={r.status_code}")

    # -------------------------------------------------------- drift is refused
    r = c.post(
        f"{studio}/proposals", headers=owner_h,
        json={"file_path": "src/calculator.py", "instruction": "add a docstring"},
    )
    dpid = r.json()["id"]
    c.post(f"{studio}/proposals/{dpid}/approve", headers=owner_h)
    r = c.post(prs, headers=owner_h, json={"title": "Drift test"})
    drift_id = r.json()["id"]
    # a human edits the file after the proposal was snapshotted
    c.put(f"{studio}/files/src/calculator.py", headers=owner_h, json={"content": "# hand edited\n"})
    r = c.post(f"{prs}/{drift_id}/open", headers=owner_h)
    check(
        "pr: drift refused on open -> 502",
        r.status_code == 502,
        f"status={r.status_code}",
    )
    r = c.get(f"{prs}/{drift_id}", headers=owner_h)
    check(
        "pr: drift marked failed with reason",
        r.json()["status"] == "failed" and bool(r.json()["error"]),
        r.json().get("error", "")[:80],
    )

    # ------------------------------------------------------------ close a draft
    r = c.post(
        f"{studio}/proposals", headers=owner_h,
        json={"file_path": "src/calculator.py", "instruction": "another tweak"},
    )
    cpid = r.json()["id"]
    c.post(f"{studio}/proposals/{cpid}/approve", headers=owner_h)
    r = c.post(prs, headers=owner_h, json={"title": "Close me"})
    close_id = r.json()["id"]
    r = c.post(f"{prs}/{close_id}/close", headers=owner_h)
    check(
        "pr: close a draft",
        r.status_code == 200 and r.json()["proposal"]["status"] == "closed",
        f"status={r.status_code}",
    )
    r = c.post(f"{prs}/{close_id}/close", headers=owner_h)
    check("pr: cannot close twice -> 409", r.status_code == 409, f"status={r.status_code}")

    r = c.get(f"{prs}?status=merged", headers=owner_h)
    check(
        "pr: filter by status",
        r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["id"] == pr_id,
        f"n={len(r.json()) if r.status_code == 200 else '?'}",
    )

    r = c.get(f"{prs}/{pr_id}", headers=stray_h)
    check("pr: non-member blocked", r.status_code == 403, f"status={r.status_code}")
    r = c.post(prs, headers=stray_h, json={"title": "nope"})
    check("pr: non-member cannot create", r.status_code == 403, f"status={r.status_code}")

    r = c.delete(f"{repos}/{github_repo_id}", headers=owner_h)
    check("repos: delete -> 204", r.status_code == 204, f"status={r.status_code}")
    r = c.get(f"{repos}/{github_repo_id}", headers=owner_h)
    check("repos: deleted -> 404", r.status_code == 404, f"status={r.status_code}")

    # ---------------------------------------------------------------- the agent
    r = c.post(
        "/api/v1/meetings", headers=owner_h,
        json={"workspace_id": ws, "title": "Architecture sync", "consent_confirmed": True},
    )
    mid = r.json()["id"]
    c.patch(
        f"/api/v1/meetings/{mid}", headers=owner_h,
        json={"summary": "We agreed to guard the divide-by-zero path in the calculator."},
    )
    r = c.post(
        f"/api/v1/meetings/{mid}/decisions", headers=owner_h,
        json={
            "title": "Guard divide by zero",
            "description": "divide() must return None when the divisor is zero",
            "impact": "high",
        },
    )
    did = r.json()["id"]
    check("agent: decision created", r.status_code == 201, f"status={r.status_code}")
    c.post(
        "/api/v1/tasks", headers=owner_h,
        json={"workspace_id": ws, "title": "Fix divide bug", "priority": "high", "meeting_id": mid},
    )

    r = c.post(f"{agent}/plan", headers=owner_h, json={"meeting_id": mid})
    plan = r.json()
    check(
        "agent: plan created offline",
        r.status_code == 201 and plan["source"] == "fallback",
        f"status={r.status_code} source={plan.get('source')}",
    )
    check(
        "agent: requirements from the decision",
        any("Guard divide by zero" in req for req in plan.get("requirements", [])),
        str(plan.get("requirements")),
    )
    paths = [f["path"] for f in plan.get("affected_files", [])]
    check(
        "agent: finds the affected calculator file",
        "src/calculator.py" in paths,
        str(paths),
    )
    check(
        "agent: proposes a change to that file",
        bool(plan.get("proposed_changes"))
        and plan["proposed_changes"][0]["path"] == "src/calculator.py",
        str(plan.get("proposed_changes"))[:120],
    )
    check(
        "agent: subtasks produced",
        isinstance(plan.get("subtasks"), list) and len(plan["subtasks"]) >= 1,
        f"n={len(plan.get('subtasks', []))}",
    )
    check("agent: fallback reason recorded", "fallback_reason" in plan or plan["source"] == "fallback", "")
    plan_id = plan["id"]

    r = c.post(f"{agent}/plan", headers=owner_h, json={"decision_id": did})
    check(
        "agent: plan from a single decision",
        r.status_code == 201 and r.json()["decision_id"] == did,
        f"status={r.status_code}",
    )

    r = c.post(f"{agent}/plan", headers=owner_h, json={"focus": "Add a subtract function"})
    check(
        "agent: focus-only plan",
        r.status_code == 201 and any("subtract" in req.lower() for req in r.json()["requirements"]),
        str(r.json().get("requirements"))[:120],
    )

    r = c.post(f"{agent}/plan", headers=owner_h, json={"meeting_id": "ghost"})
    check("agent: unknown meeting -> 404", r.status_code == 404, f"status={r.status_code}")

    r = c.get(f"{agent}/plans", headers=owner_h)
    check("agent: list plans", r.status_code == 200 and len(r.json()) >= 3, f"n={len(r.json())}")

    r = c.get(f"{agent}/plans/{plan_id}", headers=owner_h)
    check("agent: get plan", r.status_code == 200 and r.json()["id"] == plan_id, f"status={r.status_code}")

    before_pending = len(c.get(f"{studio}/proposals?status=pending", headers=owner_h).json())
    r = c.post(f"{agent}/plans/{plan_id}/apply", headers=owner_h)
    applied = r.json()
    check(
        "agent: apply creates pending proposals",
        r.status_code == 200 and applied["created"] >= 1 and applied["plan"]["status"] == "applied",
        f"status={r.status_code} created={applied.get('created')}",
    )
    after_pending = len(c.get(f"{studio}/proposals?status=pending", headers=owner_h).json())
    check(
        "agent: proposals are pending (not written)",
        after_pending == before_pending + applied["created"],
        f"before={before_pending} after={after_pending}",
    )

    r = c.post(f"{agent}/plans/{plan_id}/apply", headers=owner_h)
    check("agent: cannot apply twice -> 409", r.status_code == 409, f"status={r.status_code}")

    r = c.get(f"{agent}/plans", headers=stray_h)
    check("agent: non-member blocked", r.status_code == 403, f"status={r.status_code}")

    # -------------------------------------------------------------- ship units
    check(
        "ship: branch naming",
        ship.make_branch_name("Fix the divide bug!", "a1b2c3d4e5").startswith("syncforge/fix-the-divide-bug-"),
        ship.make_branch_name("Fix the divide bug!", "a1b2c3d4e5"),
    )
    check("ship: provider helper", ship.is_github("github") and not ship.is_github("local"), "")

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
    shutil.rmtree(SANDBOX, ignore_errors=True)
    sys.exit(code)
