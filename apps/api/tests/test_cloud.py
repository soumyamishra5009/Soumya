"""Cloud/serverless smoke tests — the exact configuration that runs on Vercel.

* ``DEVSTUDIO_BACKEND=db``  — the Dev Studio tree lives as ``WorkspaceFile``
  rows (no writable persistent filesystem on serverless)
* ``CODE_EXECUTOR=local``   — the bundled runner executes via subprocess in a
  temp directory materialised from the DB sandbox (allowed on Vercel Functions
  with a writable /tmp; no external service, no extra API key)
* SQLite stands in for Vercel Postgres: ``init_db`` -> ``create_all`` is
  identical on both engines, so table creation (including ``workspace_files``)
  is validated here.

No network access is required. Run from apps/api:  python tests/test_cloud.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = os.path.join(tempfile.gettempdir(), f"cloud_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.replace(os.sep, '/')}"
os.environ["DEVSTUDIO_BACKEND"] = "db"
os.environ["CODE_EXECUTOR"] = "local"
# Deterministic offline mode for the LLM ladder (no network dependency).
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.services import devstudio, testrunner  # noqa: E402
from app.services.devstudio_store import DbStore, get_store  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


def register(c: TestClient, name: str) -> dict[str, str]:
    email = f"{name.lower()}+{uuid.uuid4().hex[:6]}@example.com"
    r = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": name},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def run() -> int:
    from app.core.database import SessionLocal, init_db

    # create_all must register workspace_files (models/__init__ imports it).
    init_db()
    c = TestClient(main.app)

    # ------------------------------------------------------------------ startup
    r = c.get("/health")
    check(
        "cloud: app starts with db backend",
        r.status_code == 200 and r.json().get("database") == "ok",
        f"status={r.status_code}",
    )

    h = register(c, "CloudOwner")
    ws = c.post("/api/v1/workspaces", headers=h, json={"name": "Cloud WS"}).json()["id"]
    base = f"/api/v1/workspaces/{ws}/studio"

    # ------------------------------------------------- DbStore through the HTTP layer
    r = c.get(f"{base}/tree", headers=h)
    check("db: tree empty initially", r.status_code == 200 and r.json()["empty"] is True, f"status={r.status_code}")

    r = c.post(f"{base}/seed", headers=h)
    check(
        "db: seed sample over HTTP",
        r.status_code == 201 and len(r.json()["created"]) == 4,
        f"status={r.status_code} created={r.json().get('created') if r.status_code == 201 else ''}",
    )

    r = c.get(f"{base}/tree", headers=h)
    paths = set(devstudio.flatten_paths(r.json(), 100)) if r.status_code == 200 else set()
    check(
        "db: tree lists sample files",
        {"README.md", "src/calculator.py", "tests/test_calculator.py"} <= paths,
        str(sorted(paths)),
    )

    r = c.get(f"{base}/files/src/calculator.py", headers=h)
    check(
        "db: read file over HTTP",
        r.status_code == 200 and "def divide" in r.json().get("content", ""),
        f"status={r.status_code}",
    )

    r = c.put(
        f"{base}/files/src/calculator.py",
        headers=h,
        json={"content": "# edited in cloud mode\n"},
    )
    check("db: write file over HTTP", r.status_code == 200, f"status={r.status_code}")
    r = c.get(f"{base}/files/src/calculator.py", headers=h)
    check("db: write persisted", r.json().get("content", "").startswith("# edited"), "")

    # ------------------------------------------------------ DbStore service surface
    db = SessionLocal()
    try:
        store = get_store(db)
        check("db: get_store returns DbStore", isinstance(store, DbStore), type(store).__name__)
        check(
            "db: read_content sees HTTP write",
            (store.read_content(ws, "src/calculator.py") or "").startswith("# edited"),
            "",
        )
        check("db: read_content missing -> None", store.read_content(ws, "nope.py") is None)
        check("db: file_exists", store.file_exists(ws, "tests/test_calculator.py"))
        store.create_dir(ws, "docs")
        store.create_file(ws, "docs/plan.md", "# plan\n")
        allf = {f["path"] for f in store.get_all_files(ws)}
        check("db: get_all_files returns tree", {"docs/plan.md", "src/calculator.py"} <= allf, str(len(allf)))
        store.delete_entry(ws, "docs")
        check("db: delete removes dir", not store.file_exists(ws, "docs/plan.md"))
        check(
            "db: traversal rejected",
            not store.file_exists(ws, "../../etc/passwd"),
            "",
        )

        # Restore the real sample (the HTTP write above replaced calculator.py).
        devstudio.seed_sample(ws, db=db)  # skips existing, so rewrite explicitly
        sample = next(
            (v for k, v in devstudio.SAMPLE_FILES.items() if k == "src/calculator.py"),
            "",
        )
        store.write_file(ws, "src/calculator.py", sample)

        # ------------------------------------- cloud executor e2e (no network)
        # CODE_EXECUTOR=local + DEVSTUDIO_BACKEND=db: the DB sandbox is
        # materialised into a temp dir and the bundled runner executes there —
        # the same path Vercel Functions use (subprocess + writable /tmp).
        tmp_before = {p.name for p in Path(tempfile.gettempdir()).glob("syncforge_ws_*")}
        result = testrunner.run_tests(ws, kind="python")
        check("cloud run: source label", result.get("source") == "local", str(result.get("source")))
        check(
            "cloud run: sample bug detected (4 pass / 1 fail)",
            result.get("passed") == 4 and result.get("failed") == 1,
            f"passed={result.get('passed')} failed={result.get('failed')} errors={result.get('errors')}",
        )
        check("cloud run: status=failed", result.get("status") == "failed", str(result.get("status")))
        check("cloud run: kind=python", result.get("kind") == "python", str(result.get("kind")))
        check(
            "cloud run: output captured",
            isinstance(result.get("output"), str) and len(result["output"]) > 0,
            "",
        )

        # Apply the divide-by-zero fix (what the AI proposal would write)
        # and rerun — the full loop must go green in cloud mode.
        fixed = (store.read_content(ws, "src/calculator.py") or "").replace(
            "    return a / b",
            "    if b == 0:\n        return None\n    return a / b",
        )
        store.write_file(ws, "src/calculator.py", fixed)
        result2 = testrunner.run_tests(ws, kind="python")
        check(
            "cloud run: all green after fix (5 pass)",
            result2.get("passed") == 5 and result2.get("failed") == 0,
            f"passed={result2.get('passed')} failed={result2.get('failed')}",
        )
        check("cloud run: status=passed", result2.get("status") == "passed", str(result2.get("status")))

        # Targeted single-file run through the same path.
        result3 = testrunner.run_tests(ws, kind="python", target="tests/test_calculator.py")
        check(
            "cloud run: targeted run",
            result3.get("target") == "tests/test_calculator.py" and result3.get("passed") == 5,
            f"target={result3.get('target')} passed={result3.get('passed')}",
        )

        # The materialised temp sandbox must be cleaned up after every run.
        tmp_after = {p.name for p in Path(tempfile.gettempdir()).glob("syncforge_ws_*")}
        check("cloud run: temp sandbox cleaned up", tmp_after <= tmp_before, str(tmp_after - tmp_before))

        # The optional Piston executor stays wired up: its entry-script builder
        # must emit valid Python (the public instance requires a token since
        # Feb 2026, so the live call itself is not exercised here).
        entry = testrunner._piston_entry_script(store.get_all_files(ws), "src/calculator.py")
        try:
            compile(entry, "main.py", "exec")
            entry_ok = True
        except SyntaxError:
            entry_ok = False
        check("piston entry script compiles", entry_ok)
        check(
            "kind detection: python via path list",
            testrunner._detect_kind_from_paths(["tests/test_calculator.py"], None) == "python",
        )
        check(
            "kind detection: node via package.json",
            testrunner._detect_kind_from_paths(["package.json", "src/app.js"], None) == "node",
        )
    finally:
        db.rollback()
        db.close()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run())
