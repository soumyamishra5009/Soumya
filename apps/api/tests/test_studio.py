"""Phase 3 Dev Studio tests: sandbox, AI chat fallback, change proposals.

Run from apps/api:  python tests/test_studio.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = os.path.join(tempfile.gettempdir(), f"test_{uuid.uuid4().hex}.db")
SANDBOX = os.path.join(tempfile.gettempdir(), f"studio_{uuid.uuid4().hex}")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.replace(os.sep, '/')}"
os.environ["DEVSTUDIO_ROOT"] = SANDBOX.replace(os.sep, "/")
# Deterministic offline mode: point the LLM ladder at a closed port so the
# Dev Studio's deterministic fallbacks are exercised (no network dependency).
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["ALLOW_EXTRACTIVE_FALLBACK"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.services import devstudio  # noqa: E402

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

    owner_h = register(c, "DevOwner")[1]
    stray_h = register(c, "DevStray")[1]

    ws = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Studio WS"}).json()["id"]
    ws2 = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Other WS"}).json()["id"]
    base = f"/api/v1/workspaces/{ws}/studio"

    # ------------------------------------------------------------- sandbox units
    for bad in ("../secret.txt", "a/../../b.txt", "/etc/passwd", "C:/Windows/win.ini", "~/.ssh/id_rsa"):
        try:
            devstudio.resolve_path(ws, bad)
            check(f"sandbox: blocks {bad!r}", False, "no error raised")
        except devstudio.SandboxError:
            check(f"sandbox: blocks {bad!r}", True, "")

    try:
        devstudio.write_file(ws, "payload.bin", "binary")
        check("sandbox: non-text extension rejected", False, "write succeeded")
    except devstudio.SandboxError:
        check("sandbox: non-text extension rejected", True, "")

    try:
        devstudio.write_file(ws, ".env", "SECRET=1")
        check("sandbox: dotfile rejected", False, "write succeeded")
    except devstudio.SandboxError:
        check("sandbox: dotfile rejected", True, "")

    check(
        "sandbox: .env.example allowed",
        devstudio.is_editable(".env.example") and devstudio.is_editable("Dockerfile"),
        "",
    )
    check(
        "sandbox: language detection",
        devstudio.language_for("a/b.tsx") == "typescript"
        and devstudio.language_for("Makefile") == "makefile"
        and devstudio.language_for("x.unknown") == "plaintext",
        "",
    )
    check(
        "sandbox: diff stats",
        devstudio.diff_stats("a\nb\n", "a\nc\nd\n") == (2, 1),
        str(devstudio.diff_stats("a\nb\n", "a\nc\nd\n")),
    )

    # ---------------------------------------------------------------- tree / seed
    r = c.get(f"{base}/tree", headers=owner_h)
    check("tree: empty workspace", r.status_code == 200 and r.json()["empty"] is True, f"status={r.status_code}")

    r = c.post(f"{base}/seed", headers=owner_h)
    check(
        "seed: sample project created",
        r.status_code == 201 and len(r.json()["created"]) == 4,
        f"created={r.json().get('created') if r.status_code == 201 else r.status_code}",
    )

    r = c.post(f"{base}/seed", headers=owner_h)
    check(
        "seed: idempotent (skips existing)",
        r.status_code == 201 and r.json()["created"] == [] and r.json()["skipped"] == 4,
        "",
    )

    r = c.get(f"{base}/tree", headers=owner_h)
    tree = r.json()
    paths = set(devstudio.flatten_paths(tree, 100))
    check(
        "tree: lists sample files",
        {"README.md", "src/calculator.py", "tests/test_calculator.py", "notes/meeting-actions.md"} <= paths,
        str(sorted(paths)),
    )
    check("tree: nested dirs present", any(ch["type"] == "dir" for ch in tree["children"]), "")

    r = c.get(f"/api/v1/workspaces/{ws2}/studio/tree", headers=owner_h)
    check("tree: isolated per workspace", r.json()["empty"] is True, "")

    # ------------------------------------------------------------------- files
    r = c.get(f"{base}/files/src/calculator.py", headers=owner_h)
    check(
        "file: read with language",
        r.status_code == 200 and r.json()["language"] == "python" and "def divide" in r.json()["content"],
        f"status={r.status_code}",
    )
    check("file: hash returned", len(r.json()["hash"]) == 64, "")

    r = c.get(f"{base}/files/nope.py", headers=owner_h)
    check("file: missing -> 404", r.status_code == 404, f"status={r.status_code}")

    r = c.get(f"{base}/files/README.md", headers=owner_h)
    original_readme = r.json()["content"]
    r = c.put(f"{base}/files/README.md", headers=owner_h, json={"content": "# Edited\n"})
    check(
        "file: write updates content",
        r.status_code == 200 and r.json()["content"] == "# Edited\n",
        f"status={r.status_code}",
    )
    c.put(f"{base}/files/README.md", headers=owner_h, json={"content": original_readme})

    r = c.put(f"{base}/files/newdir/deep/file.py", headers=owner_h, json={"content": "x = 1\n"})
    check(
        "file: write creates parent dirs",
        r.status_code == 200 and r.json()["path"] == "newdir/deep/file.py",
        f"status={r.status_code}",
    )

    r = c.post(f"{base}/files", headers=owner_h, json={"path": "src/extra.py", "kind": "file", "content": ""})
    check("file: create", r.status_code == 201, f"status={r.status_code}")

    r = c.post(f"{base}/files", headers=owner_h, json={"path": "src/extra.py", "kind": "file"})
    check("file: create duplicate -> 400", r.status_code == 400, f"status={r.status_code}")

    r = c.post(f"{base}/files", headers=owner_h, json={"path": "docs", "kind": "dir"})
    check("file: create dir", r.status_code == 201 and r.json()["type"] == "dir", f"status={r.status_code}")

    r = c.post(f"{base}/files", headers=owner_h, json={"path": "bad.bin", "kind": "file"})
    check("file: non-text create blocked", r.status_code == 400, f"status={r.status_code}")

    # Encoded traversal through real HTTP (httpx would normalise a literal "../")
    r = c.get(f"{base}/files/%2e%2e%2f%2e%2e%2fsecret.txt", headers=owner_h)
    check("file: HTTP traversal blocked", r.status_code == 400, f"status={r.status_code}")

    big = "x" * (600 * 1024)
    r = c.put(f"{base}/files/src/extra.py", headers=owner_h, json={"content": big})
    check("file: size cap enforced", r.status_code == 400, f"status={r.status_code}")

    r = c.delete(f"{base}/files/newdir", headers=owner_h)
    check("file: delete dir recursively", r.status_code == 200 and r.json()["type"] == "dir", f"status={r.status_code}")

    r = c.delete(f"{base}/files/src/extra.py", headers=owner_h)
    check("file: delete file", r.status_code == 200, f"status={r.status_code}")

    r = c.delete(f"{base}/files/src/extra.py", headers=owner_h)
    check("file: delete twice -> 404", r.status_code == 404, f"status={r.status_code}")

    # The sandbox root is never deletable (checked at the service layer, since
    # an empty path never reaches the HTTP route).
    for bad in (".", "./", ""):
        try:
            devstudio.delete_entry(ws, bad)
            check(f"sandbox: refuses to delete root {bad!r}", False, "no error raised")
        except devstudio.SandboxError:
            check(f"sandbox: refuses to delete root {bad!r}", True, "")

    r = c.delete(f"{base}/files/notes/meeting-actions.md", headers=owner_h)
    check("file: delete removes file", r.status_code == 200, f"status={r.status_code}")
    check(
        "file: deleted file is gone",
        c.get(f"{base}/files/notes/meeting-actions.md", headers=owner_h).status_code == 404,
        "",
    )

    # -------------------------------------------------------------------- lint
    r = c.post(
        f"{base}/lint?path=src/calculator.py",
        headers=owner_h,
        json={"content": "def f(a=[]):\n    if a == None:\n        pass\n"},
    )
    messages = " ".join(f["message"] for f in r.json()["findings"])
    check(
        "lint: finds mutable default + == None",
        r.status_code == 200 and "Mutable default" in messages and "is None" in messages,
        f"n={len(r.json()['findings'])}",
    )

    r = c.post(
        f"{base}/lint?path=src/calculator.py",
        headers=owner_h,
        json={"content": "def f(a=[]):\n    try:\n        pass\n    except:\n        pass\n"},
    )
    findings = r.json()["findings"]
    check(
        "lint: bare except flagged high severity",
        r.status_code == 200
        and findings[0]["severity"] == "high"
        and "Bare `except:`" in findings[0]["message"],
        str(findings[:1]),
    )

    # -------------------------------------------------------------------- chat
    r = c.post(
        f"{base}/chat",
        headers=owner_h,
        json={"message": "Explain what this file does", "file_path": "src/calculator.py"},
    )
    body = r.json()
    check(
        "chat: offline fallback answers",
        r.status_code == 200 and body["source"] == "fallback" and "Offline mode" in body["answer"],
        f"status={r.status_code} source={body.get('source')}",
    )
    check(
        "chat: uses file context",
        "calculator.py" in body["answer"] and body["context_used"]["file_path"] == "src/calculator.py",
        str(body["context_used"]),
    )
    check("chat: fallback_reason recorded", bool(body.get("fallback_reason")), "")

    r = c.post(
        f"{base}/chat",
        headers=owner_h,
        json={"message": "review this file for bugs", "file_path": "src/calculator.py"},
    )
    check(
        "chat: offline review returns findings + suggestion",
        r.status_code == 200
        and "finding(s)" in r.json()["answer"]
        and any(s["action"] == "propose_edit" for s in r.json()["suggestions"]),
        f"n_suggestions={len(r.json()['suggestions'])}",
    )

    r = c.post(f"{base}/chat", headers=owner_h, json={"message": "what is in this project?"})
    check(
        "chat: project overview without a file",
        r.status_code == 200 and "src/calculator.py" in r.json()["answer"],
        "",
    )

    # chat can consume meeting + task context
    mid = c.post(
        "/api/v1/meetings",
        headers=owner_h,
        json={
            "workspace_id": ws,
            "title": "Architecture sync",
            "consent_confirmed": True,
            "participants": ["Owner"],
        },
    ).json()["id"]
    c.patch(
        f"/api/v1/meetings/{mid}",
        headers=owner_h,
        json={"summary": "We agreed to guard divide-by-zero."},
    )
    tid = c.post(
        "/api/v1/tasks",
        headers=owner_h,
        json={"workspace_id": ws, "title": "Fix divide bug", "priority": "high"},
    ).json()["id"]

    r = c.post(
        f"{base}/chat",
        headers=owner_h,
        json={
            "message": "what should I do next?",
            "file_path": "src/calculator.py",
            "meeting_id": mid,
            "task_id": tid,
            "history": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        },
    )
    ctx = r.json()["context_used"]
    check(
        "chat: links meeting + task context",
        r.status_code == 200 and ctx["meeting_linked"] is True and ctx["task_linked"] is True,
        str(ctx),
    )

    # ------------------------------------------------------------- proposals
    r = c.post(f"{base}/chat", headers=owner_h, json={"message": "hi", "meeting_id": "ghost"})
    check("chat: unknown meeting ignored", r.status_code == 200 and r.json()["context_used"]["meeting_linked"] is False, "")

    r = c.post(
        f"{base}/proposals",
        headers=owner_h,
        json={
            "file_path": "src/calculator.py",
            "instruction": "guard against division by zero",
            "meeting_id": mid,
            "task_id": tid,
        },
    )
    proposal = r.json()
    pid = proposal.get("id", "")
    check(
        "proposal: created pending (offline scaffold)",
        r.status_code == 201 and proposal["status"] == "pending" and proposal["source"] == "fallback",
        f"status={r.status_code} src={proposal.get('source')}",
    )
    check(
        "proposal: captures base hash + diff stats",
        bool(proposal["base_hash"]) and proposal["added_lines"] > 0,
        f"added={proposal.get('added_lines')} removed={proposal.get('removed_lines')}",
    )
    check(
        "proposal: links meeting + task",
        proposal["meeting_id"] == mid and proposal["task_id"] == tid,
        "",
    )

    r = c.get(f"{base}/proposals?status=pending", headers=owner_h)
    check("proposal: list pending", r.status_code == 200 and pid in [p["id"] for p in r.json()], f"n={len(r.json())}")

    r = c.get(f"{base}/proposals?status=approved", headers=owner_h)
    check("proposal: list filter by status", r.status_code == 200 and r.json() == [], "")

    # rejection leaves the file untouched
    before = c.get(f"{base}/files/src/calculator.py", headers=owner_h).json()["content"]
    r = c.post(f"{base}/proposals/{pid}/reject", headers=owner_h)
    check(
        "proposal: reject marks rejected",
        r.status_code == 200 and r.json()["proposal"]["status"] == "rejected" and r.json()["applied"] is False,
        f"status={r.status_code}",
    )
    after = c.get(f"{base}/files/src/calculator.py", headers=owner_h).json()["content"]
    check("proposal: reject does not write", before == after, "")

    r = c.post(f"{base}/proposals/{pid}/reject", headers=owner_h)
    check("proposal: double decide -> 409", r.status_code == 409, f"status={r.status_code}")

    # approval writes exactly the proposed content
    r = c.post(
        f"{base}/proposals",
        headers=owner_h,
        json={"file_path": "src/calculator.py", "instruction": "add a comment explaining divide"},
    )
    pid2 = r.json()["id"]
    proposed = r.json()["proposed_content"]

    r = c.post(f"{base}/proposals/{pid2}/approve", headers=owner_h)
    check(
        "proposal: approve applies",
        r.status_code == 200 and r.json()["applied"] is True and r.json()["proposal"]["status"] == "approved",
        f"status={r.status_code} {r.json().get('message', '')}",
    )
    written = c.get(f"{base}/files/src/calculator.py", headers=owner_h).json()["content"]
    check("proposal: file matches proposed content", written == proposed, "")

    r = c.post(f"{base}/proposals/{pid2}/approve", headers=owner_h)
    check("proposal: double approve -> 409", r.status_code == 409, f"status={r.status_code}")

    # stale proposals are refused
    r = c.post(
        f"{base}/proposals",
        headers=owner_h,
        json={"file_path": "src/calculator.py", "instruction": "another tweak"},
    )
    pid3 = r.json()["id"]
    c.put(f"{base}/files/src/calculator.py", headers=owner_h, json={"content": "# changed by a human\n"})
    r = c.post(f"{base}/proposals/{pid3}/approve", headers=owner_h)
    check("proposal: stale approve -> 409", r.status_code == 409, f"status={r.status_code}")

    # proposals for files that do not exist yet
    r = c.post(
        f"{base}/proposals",
        headers=owner_h,
        json={"file_path": "src/new_module.py", "instruction": "create a test scaffold"},
    )
    check(
        "proposal: create-style for missing file",
        r.status_code == 201 and r.json()["original_content"] is None,
        f"status={r.status_code}",
    )
    pid4 = r.json()["id"]
    r = c.post(f"{base}/proposals/{pid4}/approve", headers=owner_h)
    check("proposal: approve creates the file", r.status_code == 200, f"status={r.status_code}")
    check(
        "proposal: created file is readable",
        c.get(f"{base}/files/src/new_module.py", headers=owner_h).status_code == 200,
        "",
    )

    r = c.get(f"{base}/proposals/does-not-exist", headers=owner_h)
    check("proposal: unknown id -> 404", r.status_code == 404, f"status={r.status_code}")

    r = c.post(
        f"{base}/proposals",
        headers=owner_h,
        json={"file_path": "../escape.py", "instruction": "nope"},
    )
    check("proposal: traversal path blocked", r.status_code == 400, f"status={r.status_code}")

    # ------------------------------------------------------------ permissions
    r = c.get(f"{base}/tree", headers=stray_h)
    check("perm: non-member cannot read tree", r.status_code == 403, f"status={r.status_code}")
    r = c.post(f"{base}/chat", headers=stray_h, json={"message": "hi"})
    check("perm: non-member cannot chat", r.status_code == 403, f"status={r.status_code}")
    r = c.post(
        f"{base}/proposals",
        headers=stray_h,
        json={"file_path": "src/calculator.py", "instruction": "hi"},
    )
    check("perm: non-member cannot propose", r.status_code == 403, f"status={r.status_code}")
    r = c.get(f"{base}/tree")
    check("perm: anonymous rejected", r.status_code == 401, f"status={r.status_code}")

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
    for path in (TEST_DB,):
        try:
            os.remove(path)
        except OSError:
            pass
    import shutil

    shutil.rmtree(SANDBOX, ignore_errors=True)
    sys.exit(code)
