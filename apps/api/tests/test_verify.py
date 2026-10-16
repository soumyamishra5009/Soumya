"""Phase 5 tests: sandboxed test runs (verification).

Covers the bundled dependency-free runner, output parsing, sandbox safety
(traversal, .git, secret-free environment), timeouts, the HTTP surface and the
"fail → fix → pass" loop.

Run from apps/api:  python tests/test_verify.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = os.path.join(tempfile.gettempdir(), f"test_verify_{uuid.uuid4().hex}.db")
SANDBOX = os.path.join(tempfile.gettempdir(), f"verify_{uuid.uuid4().hex}")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.replace(os.sep, '/')}"
os.environ["DEVSTUDIO_ROOT"] = SANDBOX.replace(os.sep, "/")
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["GITHUB_TOKEN"] = ""
os.environ["ALLOW_EXTRACTIVE_FALLBACK"] = "true"

from pathlib import Path  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.services import devstudio, testrunner  # noqa: E402

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


FIXED_CALCULATOR = '''"""Sample calculator module for the Dev Studio walkthrough."""


def add(a, b):
    return a + b


def divide(a, b):
    if b == 0:
        return None
    return a / b


def is_zero(value):
    return value is None


def average(values=None):
    if not values:
        return 0
    return sum(values) / len(values)


def describe(values):
    return f"{len(values)} value(s), average {average(values):.2f}"
'''

SLOW_TEST = """import time


def test_slow():
    time.sleep(10)
"""


def run() -> int:
    from app.core.database import init_db

    init_db()
    c = TestClient(main.app)

    root = devstudio.workspace_root("probe")  # not created; used for env checks

    # ------------------------------------------------------------ unit: parse
    check(
        "parse: builtin marker",
        testrunner.parse_counts("junk\nSYNCFORGE_RESULT passed=4 failed=1 errors=0") == (4, 1, 0),
        "",
    )
    check(
        "parse: pytest summary",
        testrunner.parse_counts("1 failed, 4 passed in 0.05s") == (4, 1, 0),
        "",
    )
    check(
        "parse: pytest errors",
        testrunner.parse_counts("2 errors in 0.01s") == (0, 0, 2),
        "",
    )
    check(
        "parse: node summary",
        testrunner.parse_counts("# tests 3\n# pass 2\n# fail 1\n") == (2, 1, 0),
        "",
    )
    check("parse: unknown -> zeros", testrunner.parse_counts("nothing here") == (0, 0, 0), "")
    check("parse: detects no-tests", testrunner.has_no_tests("SYNCFORGE_NO_TESTS"), "")
    check("parse: no false no-tests", not testrunner.has_no_tests("5 passed"), "")

    # ---------------------------------------------------------- unit: helpers
    check("timeout: clamps low", testrunner._timeout(1) == 5, "")
    check("timeout: clamps high", testrunner._timeout(9999) == 300, "")
    check("timeout: honours value", testrunner._timeout(45) == 45, "")

    os.environ["GITHUB_TOKEN"] = "super-secret-token"
    os.environ["OPENROUTER_API_KEY"] = "sk-secret"
    env = testrunner._child_env(root)
    check("env: withholds GITHUB_TOKEN", "GITHUB_TOKEN" not in env, "")
    check("env: withholds OPENROUTER_API_KEY", "OPENROUTER_API_KEY" not in env, "")
    check("env: sets PYTHONPATH to sandbox", env.get("PYTHONPATH") == str(root), env.get("PYTHONPATH", ""))
    check("env: disables bytecode", env.get("PYTHONDONTWRITEBYTECODE") == "1", "")
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("OPENROUTER_API_KEY", None)

    short, cut = testrunner._truncate_output("hello", 100)
    check("truncate: short unchanged", short == "hello" and cut is False, "")
    long_text = "x" * 5000
    short, cut = testrunner._truncate_output(long_text, 1000)
    check("truncate: long bounded", len(short) < 1100 and cut is True, f"len={len(short)}")

    empty = Path(tempfile.mkdtemp(prefix="verify_empty_"))
    check("detect: empty dir -> None", testrunner.detect_kind(empty) is None, "")
    shutil.rmtree(empty, ignore_errors=True)
    check("detect: .py target -> python", testrunner.detect_kind(root, "a/b.py") == "python", "")
    check("detect: .ts target -> node", testrunner.detect_kind(root, "a/b.test.ts") == "node", "")

    # ------------------------------------------------------------- HTTP setup
    owner_email, owner_h = register(c, "VerifyOwner")
    member_email, member_h = register(c, "VerifyMember")
    stray_h = register(c, "VerifyStray")[1]

    ws = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Verify WS"}).json()["id"]
    c.post(
        f"/api/v1/workspaces/{ws}/members", headers=owner_h,
        json={"email": member_email, "role": "member"},
    )
    studio = f"/api/v1/workspaces/{ws}/studio"
    tests = f"/api/v1/workspaces/{ws}/tests"

    # ------------------------------------------------------- empty sandbox run
    r = c.post(f"{tests}/run", headers=owner_h, json={})
    check("run: empty sandbox -> 400", r.status_code == 400, f"status={r.status_code}")

    r = c.post(f"{studio}/seed", headers=owner_h)
    check("studio: sample seeded", r.status_code == 201 and len(r.json()["created"]) == 4, "")

    # ---------------------------------------------------------------- first run
    r = c.post(f"{tests}/run", headers=owner_h, json={})
    body = r.json()
    check("run: 201 created", r.status_code == 201, f"status={r.status_code}")
    check("run: kind detected python", body.get("kind") == "python", str(body.get("kind")))
    expected_runner = "pytest" if testrunner.pytest_available() else "builtin"
    check("run: expected runner", body.get("runner") == expected_runner, str(body.get("runner")))
    check(
        "run: reports the failing divide test",
        body.get("status") == "failed" and body.get("passed") == 4 and body.get("failed") == 1,
        f"{body.get('passed')}/{body.get('failed')}",
    )
    check("run: exit code 1", body.get("exit_code") == 1, str(body.get("exit_code")))
    check("run: source is local", body.get("source") == "local", str(body.get("source")))
    check("run: command recorded", bool(body.get("command")), body.get("command", "")[:60])
    check("run: output captured", "test_divide_by_zero_returns_none" in body.get("output", ""), "")
    check("run: summary mentions failure", "fail" in body.get("summary", "").lower(), body.get("summary", ""))
    run_id = body["id"]

    # ------------------------------------------------------------- read back
    r = c.get(f"{tests}/latest", headers=owner_h)
    check("latest: returns newest run", r.status_code == 200 and r.json()["id"] == run_id, "")
    r = c.get(tests, headers=owner_h)
    check("list: one run", r.status_code == 200 and len(r.json()) == 1, f"n={len(r.json())}")
    r = c.get(f"{tests}/{run_id}", headers=owner_h)
    check("get: by id", r.status_code == 200 and r.json()["id"] == run_id, "")
    r = c.get(f"{tests}/{uuid.uuid4()}", headers=owner_h)
    check("get: unknown id -> 404", r.status_code == 404, f"status={r.status_code}")
    r = c.get(f"{tests}?status=failed", headers=owner_h)
    check("list: filter failed", r.status_code == 200 and len(r.json()) == 1, "")
    r = c.get(f"{tests}?status=passed", headers=owner_h)
    check("list: filter passed empty", r.status_code == 200 and len(r.json()) == 0, "")

    # ------------------------------------------------------------- targeting
    r = c.post(f"{tests}/run", headers=owner_h, json={"target": "tests/test_calculator.py"})
    check(
        "run: scoped to one file",
        r.status_code == 201 and r.json()["status"] == "failed" and r.json()["failed"] == 1,
        f"status={r.status_code}",
    )
    r = c.post(f"{tests}/run", headers=owner_h, json={"target": "src/calculator.py"})
    check(
        "run: target with no tests -> error",
        r.status_code == 201 and r.json()["status"] == "error",
        f"status={r.json().get('status')}",
    )
    r = c.post(f"{tests}/run", headers=owner_h, json={"target": "../escape.py"})
    check("run: traversal target -> 400", r.status_code == 400, f"status={r.status_code}")
    r = c.post(f"{tests}/run", headers=owner_h, json={"target": ".git/config"})
    check("run: .git target -> 400", r.status_code == 400, f"status={r.status_code}")

    # ---------------------------------------------------------------- timeout
    c.put(f"{studio}/files/tests/test_slow.py", headers=owner_h, json={"content": SLOW_TEST})
    r = c.post(f"{tests}/run", headers=owner_h, json={"target": "tests/test_slow.py", "timeout": 5})
    check(
        "run: timeout is enforced",
        r.status_code == 201 and r.json()["status"] == "timeout",
        f"status={r.json().get('status')}",
    )
    c.delete(f"{studio}/files/tests/test_slow.py", headers=owner_h)

    # ----------------------------------------------------- sandbox hygiene
    sandbox = devstudio.workspace_root(ws)
    check(
        "sandbox: no __pycache__ after runs",
        not (sandbox / "__pycache__").exists() and not (sandbox / "tests" / "__pycache__").exists(),
        "",
    )
    check("sandbox: no runner file left behind", not list(sandbox.rglob("syncforge_runner*")), "")

    # --------------------------------------------------------- permissions
    r = c.post(f"{tests}/run", headers=stray_h, json={})
    check("permissions: non-member -> 403", r.status_code == 403, f"status={r.status_code}")
    r = c.post(f"{tests}/run", headers=member_h, json={})
    check("permissions: member may run", r.status_code == 201, f"status={r.status_code}")

    # --------------------------------------------------- fail -> fix -> pass
    r = c.put(
        f"{studio}/files/src/calculator.py", headers=owner_h,
        json={"content": FIXED_CALCULATOR},
    )
    check("fix: calculator.py rewritten", r.status_code == 200, f"status={r.status_code}")
    r = c.post(f"{tests}/run", headers=owner_h, json={})
    body = r.json()
    check(
        "run: all green after the fix",
        body["status"] == "passed" and body["failed"] == 0 and body["passed"] == 5,
        f"{body.get('passed')}/{body.get('failed')}",
    )
    check("run: summary reports success", "passed" in body.get("summary", "").lower(), body.get("summary", ""))

    # ------------------------------------------------------------- deletion
    r = c.delete(f"{tests}/{run_id}", headers=owner_h)
    check("delete: run removed", r.status_code == 204, f"status={r.status_code}")
    r = c.get(f"{tests}/{run_id}", headers=owner_h)
    check("delete: gone -> 404", r.status_code == 404, f"status={r.status_code}")

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n---")
    print(f"{passed}/{len(RESULTS)} passed")
    failed = [n for n, ok, _ in RESULTS if not ok]
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass
    code = run()
    try:
        os.remove(TEST_DB)
    except OSError:
        pass
    shutil.rmtree(SANDBOX, ignore_errors=True)
    sys.exit(code)
