"""Sandboxed test execution — the "verification" step of the pipeline.

A run happens inside the workspace's Dev Studio sandbox as a plain subprocess:

* disk backend — rooted at ``DEVSTUDIO_ROOT/<workspace_id>``;
* db backend (Vercel/serverless) — the tree is materialised from the database
  into a temp directory, run there, then removed (Functions allow subprocess
  with a writable /tmp).

Two Python runners:

* **builtin** — a bundled, dependency-free runner (no pytest required) that
  collects ``test_*`` functions and ``unittest.TestCase`` classes, runs them and
  prints a machine-readable summary. This is the offline default so the feature
  works on a bare machine.
* **pytest** — used automatically when pytest is importable (``EXEC_PREFER_PYTEST``).
* **node** — Node's built-in ``node --test`` runner for JavaScript projects.

An optional remote executor (``CODE_EXECUTOR=piston``) posts a single entry
script to the Piston API; it needs ``PISTON_API_KEY`` since Feb 2026.

Hard rules, mirroring the rest of the sandbox code:

* arguments are always passed as a list — never through a shell;
* the child gets a *whitelisted* environment, so workspace code can never read
  the API's secrets (``GITHUB_TOKEN``, ``DATABASE_URL``, provider keys);
* a wall-clock timeout kills the run (``EXEC_TIMEOUT_SECONDS``);
* ``stdout``/``stderr`` are captured, bounded and returned for a human to read.

Nothing here mutates the sandbox other than the byte-code/pytest caches the
runner is told not to write.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models.enums import TestRunStatus
from app.services import devstudio

logger = logging.getLogger(__name__)

KINDS = ("auto", "python", "node")

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".syncforge", "dist", "build",
}

# Only these environment variables reach the child process. Everything else —
# tokens, database URLs, provider keys — is deliberately withheld.
_ENV_KEYS = (
    "PATH", "PATHEXT", "SystemRoot", "SYSTEMROOT", "windir", "COMSPEC",
    "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA",
    "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "OS", "LANG", "LC_ALL",
)


class TestRunError(RuntimeError):
    """Raised when a run cannot be started (bad target, no interpreter)."""


# --------------------------------------------------------------------------
# Bundled runner (no pytest needed)
# --------------------------------------------------------------------------

BUILTIN_RUNNER = '''"""SyncForge bundled test runner — dependency-free.

Collects top-level ``test_*`` functions and ``unittest.TestCase`` subclasses,
executes them and prints a machine-readable summary line the API parses.
"""
import importlib.util
import inspect
import os
import sys
import traceback
import unittest


def _iter_targets(root, target):
    if target:
        yield os.path.join(root, target.replace("/", os.sep))
        return
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "env",
            ".pytest_cache", ".mypy_cache", ".ruff_cache", ".syncforge",
            "dist", "build"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip and not d.startswith("."))
        for name in sorted(filenames):
            if (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py"):
                yield os.path.join(dirpath, name)


def _iter_files(root, target):
    for path in _iter_targets(root, target):
        if os.path.isdir(path):
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = sorted(d for d in dirnames if d not in (".git", "__pycache__"))
                for name in sorted(filenames):
                    if (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py"):
                        yield os.path.join(dirpath, name)
        else:
            yield path


def _load(path, root):
    rel = os.path.relpath(path, root)
    modname = "sf_" + rel.replace(os.sep, "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


def main():
    root = os.path.abspath(sys.argv[1])
    target = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    if root not in sys.path:
        sys.path.insert(0, root)

    passed = failed = errors = 0
    failures = []
    files = list(_iter_files(root, target))

    for path in files:
        rel = os.path.relpath(path, root)
        try:
            module = _load(path, root)
        except Exception as exc:
            errors += 1
            failures.append("%s — could not import (%s: %s)" % (rel, type(exc).__name__, exc))
            traceback.print_exc()
            continue

        for name, obj in sorted(vars(module).items()):
            if name.startswith("test_") and inspect.isfunction(obj):
                args = getattr(obj, "__code__", None)
                if args is not None and (args.co_argcount or args.co_kwonlyargcount):
                    continue  # needs fixtures — not supported by the bundled runner
                label = "%s::%s" % (rel, name)
                try:
                    obj()
                    passed += 1
                    print("PASS %s" % label)
                except Exception as exc:
                    failed += 1
                    failures.append("%s — %s: %s" % (label, type(exc).__name__, exc))
                    print("FAIL %s" % label)
                    traceback.print_exc()

            elif inspect.isclass(obj) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
                suite = unittest.TestLoader().loadTestsFromTestCase(obj)
                result = unittest.TestResult()
                suite.run(result)
                total = result.testsRun
                bad = len(result.failures) + len(result.errors)
                passed += total - bad
                failed += len(result.failures)
                errors += len(result.errors)
                for case, tb in result.failures + result.errors:
                    failures.append("%s — %s" % (case, tb.strip().splitlines()[-1] if tb.strip() else "failed"))

    if failures:
        print("\\n" + "=" * 60)
        print("FAILURES")
        print("=" * 60)
        for item in failures:
            print("- %s" % item)

    if not files:
        print("No test files found (looked for test_*.py / *_test.py).")
        print("SYNCFORGE_NO_TESTS")
        print("SYNCFORGE_RESULT passed=0 failed=0 errors=0")
        return 5

    print("\\n%d passed, %d failed, %d error(s)" % (passed, failed, errors))
    print("SYNCFORGE_RESULT passed=%d failed=%d errors=%d" % (passed, failed, errors))
    return 0 if (failed == 0 and errors == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
'''


# --------------------------------------------------------------------------
# Output parsing
# --------------------------------------------------------------------------

_BUILTIN_RE = re.compile(r"SYNCFORGE_RESULT passed=(\d+) failed=(\d+) errors=(\d+)")
_PYTEST_PASSED_RE = re.compile(r"(\d+) passed")
_PYTEST_FAILED_RE = re.compile(r"(\d+) failed")
_PYTEST_ERROR_RE = re.compile(r"(\d+) errors?")
_NODE_PASS_RE = re.compile(r"^# pass (\d+)", re.MULTILINE)
_NODE_FAIL_RE = re.compile(r"^# fail (\d+)", re.MULTILINE)


def parse_counts(output: str) -> tuple[int, int, int]:
    """Return ``(passed, failed, errors)`` from runner output (0,0,0 if unknown)."""
    text = output or ""

    builtin = _BUILTIN_RE.search(text)
    if builtin:
        return int(builtin.group(1)), int(builtin.group(2)), int(builtin.group(3))

    node_pass = _NODE_PASS_RE.search(text)
    if node_pass:
        node_fail = _NODE_FAIL_RE.search(text)
        return int(node_pass.group(1)), int(node_fail.group(1)) if node_fail else 0, 0

    passed = _PYTEST_PASSED_RE.search(text)
    failed = _PYTEST_FAILED_RE.search(text)
    errors = _PYTEST_ERROR_RE.search(text)
    return (
        int(passed.group(1)) if passed else 0,
        int(failed.group(1)) if failed else 0,
        int(errors.group(1)) if errors else 0,
    )


def has_no_tests(output: str) -> bool:
    text = output or ""
    return "SYNCFORGE_NO_TESTS" in text or "no tests ran" in text.lower()


# ---------------------------------------------------------------------------
# Optional Piston remote executor (emkc.org). The public instance has required
# an authorization token since Feb 2026 — set PISTON_API_KEY to use it.
# ---------------------------------------------------------------------------

_PISTON_RUNTIME_CACHE: dict[str, str] = {}
_PISTON_LOCK = __import__("threading").Lock()


def _piston_runtime(language: str) -> tuple[str, str]:
    """Resolve ``(language, version)`` for Piston via GET /runtimes (cached).

    The public instance does not accept a wildcard version, so the exact
    version is looked up once and reused for the process lifetime.
    """
    if language in _PISTON_RUNTIME_CACHE:
        return language, _PISTON_RUNTIME_CACHE[language]

    import httpx

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{settings.PISTON_BASE_URL}/runtimes")
        resp.raise_for_status()
        runtimes = resp.json()

    wanted = language.lower()
    for rt in runtimes:
        names = [str(rt.get("language", "")).lower()]
        names += [str(a).lower() for a in rt.get("aliases", [])]
        if wanted in names:
            with _PISTON_LOCK:
                _PISTON_RUNTIME_CACHE[language] = str(rt["version"])
            return language, str(rt["version"])
    raise TestRunError(f"The Piston service has no runtime for {language!r}")


def _piston_execute(code: str, *, language: str = "python", timeout: int | None = None) -> dict[str, Any]:
    """POST a single entry script to the public Piston API and collect the run.

    Returns ``stdout``, ``stderr``, ``exit_code`` and ``timed_out``.
    """
    import httpx

    lang, version = _piston_runtime(language)
    body = {
        "language": lang,
        "version": version,
        "files": [{"name": "main.py", "content": code}],
        "stdin": "",
    }
    client_timeout = float(timeout or settings.PISTON_TIMEOUT)
    started = time.perf_counter()
    headers: dict[str, str] = {}
    if settings.PISTON_API_KEY:
        headers["Authorization"] = f"Bearer {settings.PISTON_API_KEY}"
    try:
        with httpx.Client(timeout=client_timeout) as client:
            resp = client.post(
                f"{settings.PISTON_BASE_URL}/execute", json=body, headers=headers or None
            )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        return {"stdout": "", "stderr": "piston request timed out", "exit_code": -1, "timed_out": True}
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise TestRunError(
                "The Piston API rejected the request (401 Unauthorized). The "
                "public instance has required an authorization token since "
                "Feb 2026 — set PISTON_API_KEY, or use CODE_EXECUTOR=local "
                "(the default on Vercel)."
            ) from exc
        raise TestRunError(f"Piston execution failed: {exc}") from exc
    except Exception as exc:  # network errors
        raise TestRunError(f"Piston execution could not be started: {exc}") from exc

    run = data.get("run") or {}
    compile_stage = data.get("compile") or {}
    stderr = str(run.get("stderr") or "")
    if compile_stage.get("stderr"):
        stderr = str(compile_stage["stderr"]) + ("\n" + stderr if stderr else "")

    duration_ms = int((time.perf_counter() - started) * 1000)
    # Piston reports the exit status as ``code`` (not ``exit_code``).
    exit_code = run.get("code", run.get("exit_code"))
    # Piston reports status "finished" on normal completion; a CPU-limit kill
    # comes back as an error status with a signal/killed message.
    status_detail = str((run.get("status") or {}).get("detail", ""))
    timed_out = status_detail == "TO" or "timed out" in stderr.lower()
    if timed_out and exit_code is None:
        exit_code = -1

    return {
        "stdout": str(run.get("stdout") or ""),
        "stderr": stderr,
        "exit_code": int(exit_code) if exit_code is not None else -1,
        "timed_out": bool(timed_out),
        "duration_ms": duration_ms,
    }


def _piston_entry_script(files: list[dict[str, Any]], rel_target: str | None) -> str:
    """Build a self-contained entry script for Piston.

    Piston executes exactly one entry file, so the whole workspace tree is
    embedded as base64 literals, written into the working directory on start,
    and the bundled dependency-free runner is exec'd with the same argv the
    local path uses — giving byte-identical output (SYNCFORGE_RESULT lines)
    and exit-code semantics for both modes.
    """
    payload = {f["path"]: base64.b64encode(f["content"].encode("utf-8")).decode("ascii") for f in files}
    return (
        "import base64, os, sys\n"
        f"FILES = {payload!r}\n"
        "for _rel, _b64 in FILES.items():\n"
        "    _p = os.path.abspath(_rel.replace('/', os.sep))\n"
        "    os.makedirs(os.path.dirname(_p) or '.', exist_ok=True)\n"
        "    with open(_p, 'wb') as _fh:\n"
        "        _fh.write(base64.b64decode(_b64))\n"
        f"_RUNNER = {BUILTIN_RUNNER!r}\n"
        "_root = os.path.abspath('.')\n"
        "sys.path.insert(0, _root)\n"
        "sys.argv = ['syncforge_runner.py', _root, " + repr(rel_target or "") + "]\n"
        "_ns = {'__name__': '__main__', '__file__': 'syncforge_runner.py'}\n"
        "exec(compile(_RUNNER, 'syncforge_runner.py', 'exec'), _ns)\n"
    )


def _detect_kind_from_paths(paths: list[str], target: str | None) -> str | None:
    """Same rules as :func:`detect_kind`, but over a path list (no disk)."""
    if target:
        suffix = Path(target).suffix.lower()
        if suffix == ".py":
            return "python"
        if suffix in (".js", ".mjs", ".cjs", ".ts"):
            return "node"

    names = [p.rsplit("/", 1)[-1] for p in paths]
    if any(_is_py_test(n) for n in names):
        return "python"
    if any(_is_js_test(n) for n in names):
        return "node"
    if "package.json" in names:
        return "node"
    if any(p.endswith(".py") for p in paths):
        return "python"
    return None


def _run_tests_piston(
    workspace_id: str,
    *,
    kind: str = "auto",
    target: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Run a workspace's tests through the public Piston API (cloud mode).

    Reads the sandbox via the active store (disk *or* database), so it works
    unchanged on hosts with no writable filesystem.
    """
    from app.core.database import SessionLocal
    from app.services.devstudio_store import get_store

    db = SessionLocal()
    try:
        store = get_store(db)
        files = store.get_all_files(workspace_id)
    finally:
        db.close()

    if not files:
        raise TestRunError("The workspace sandbox is empty — seed the sample project first.")

    rel_target: str | None = None
    if target:
        try:
            rel_target = devstudio.normalize_rel(target)  # rejects traversal / .git
        except Exception as exc:  # noqa: BLE001
            raise TestRunError(str(exc)) from exc
        if rel_target not in {f["path"] for f in files}:
            raise TestRunError(f"{rel_target} was not found in the sandbox")

    resolved = kind if kind != "auto" else _detect_kind_from_paths(
        [f["path"] for f in files], rel_target
    )
    if resolved is None:
        raise TestRunError(
            "Could not detect a test setup. Add a Python (test_*.py) or Node "
            "(node --test) test file, or run the bundled sample project."
        )
    if resolved == "node":
        raise TestRunError(
            "Cloud verification (CODE_EXECUTOR=piston) currently runs Python "
            "tests. For Node projects set CODE_EXECUTOR=local (container/local "
            "hosts)."
        )

    entry = _piston_entry_script(files, rel_target)
    limit = _timeout(timeout)
    result = _piston_execute(entry, language="python", timeout=limit + 15)

    output = result["stdout"]
    if result["stderr"]:
        output += ("\n" if output else "") + result["stderr"]
    exit_code = result["exit_code"]
    passed, failed, errors = parse_counts(output)

    if result["timed_out"]:
        status = TestRunStatus.TIMEOUT
        output = f"⏱️ Timed out after {limit}s (Piston CPU limit).\n\n" + output
    elif has_no_tests(output):
        status = TestRunStatus.ERROR
        output = "No tests were collected.\n\n" + output
    elif failed or errors:
        status = TestRunStatus.FAILED
    elif exit_code == 0 and passed > 0:
        status = TestRunStatus.PASSED
    elif exit_code == 0:
        status = TestRunStatus.ERROR
        output = "No tests were collected.\n\n" + output
    else:
        status = TestRunStatus.ERROR

    bounded, truncated = _truncate_output(output, settings.EXEC_MAX_OUTPUT_CHARS)

    return {
        "kind": resolved,
        "runner": "piston",
        "command": f"piston:python {settings.PISTON_BASE_URL} (bundled runner)",
        "target": rel_target,
        "status": status.value,
        "exit_code": exit_code,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "duration_ms": result.get("duration_ms", 0),
        "output": bounded,
        "output_truncated": truncated,
        "source": "piston",
    }


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def _walk_files(root: Path, limit: int = 5000) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            out.append(Path(dirpath) / name)
            if len(out) >= limit:
                return out
    return out


def _is_py_test(name: str) -> bool:
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py")


def _is_js_test(name: str) -> bool:
    return (
        (name.startswith("test_") or name.endswith(".test")) and name.endswith((".js", ".mjs", ".cjs", ".ts"))
    )


def detect_kind(root: Path, target: str | None = None) -> str | None:
    """Best-effort project type for a run: ``"python"``, ``"node"`` or ``None``."""
    if target:
        suffix = Path(target).suffix.lower()
        if suffix == ".py":
            return "python"
        if suffix in (".js", ".mjs", ".cjs", ".ts"):
            return "node"

    has_python = has_node = False
    for path in _walk_files(root):
        name = path.name
        if not has_python and _is_py_test(name):
            has_python = True
        if not has_node and _is_js_test(name):
            has_node = True
        if has_python:
            return "python"  # Python wins when both are present

    if has_node:
        return "node"
    if (root / "package.json").exists():
        return "node"
    if any(p.suffix == ".py" for p in _walk_files(root, limit=200)):
        return "python"
    return None


# --------------------------------------------------------------------------
# Process plumbing
# --------------------------------------------------------------------------

def _interp() -> str:
    return sys.executable or "python"


def _child_env(root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in _ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env["PYTHONPATH"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONHASHSEED"] = "0"
    env["NO_COLOR"] = "1"
    env["CI"] = "1"
    return env


_pytest_available: bool | None = None


def pytest_available() -> bool:
    """True when the API's interpreter can ``import pytest`` (cached)."""
    global _pytest_available
    if _pytest_available is None:
        try:
            proc = subprocess.run(
                [_interp(), "-c", "import pytest"],
                capture_output=True, text=True, timeout=20,
                stdin=subprocess.DEVNULL,
            )
            _pytest_available = proc.returncode == 0
        except Exception:  # pragma: no cover - host dependent
            _pytest_available = False
    return _pytest_available


def _truncate_output(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = limit // 3
    tail = limit - head
    return (
        text[:head]
        + f"\n\n… [{len(text) - limit} characters omitted] …\n\n"
        + text[-tail:],
        True,
    )


def _timeout(value: int | None) -> int:
    raw = value if value is not None else settings.EXEC_TIMEOUT_SECONDS
    return max(5, min(int(raw), 300))


def _run_process(
    argv: list[str], *, root: Path, timeout: int
) -> tuple[subprocess.CompletedProcess[str] | None, bool, int]:
    """Run argv with a hard timeout. Returns ``(proc, timed_out, duration_ms)``."""
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_child_env(root),
            stdin=subprocess.DEVNULL,
        )
        duration = int((time.perf_counter() - started) * 1000)
        return proc, False, duration
    except subprocess.TimeoutExpired as exc:
        duration = int((time.perf_counter() - started) * 1000)
        partial = ""
        if exc.stdout:
            partial = exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", "replace")
        if exc.stderr:
            err = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", "replace")
            partial += "\n" + err
        logger.warning("test run timed out after %ss", timeout)
        return _Partial(partial), True, duration
    except FileNotFoundError as exc:
        raise TestRunError(f"The test runner could not be started: {exc}") from exc


class _Partial:
    """Minimal stand-in for CompletedProcess when a run is killed at the timeout."""

    def __init__(self, output: str) -> None:
        self.stdout = output
        self.stderr = ""
        self.returncode: int | None = None


def _display(argv: list[str], root: Path) -> str:
    shown = [a if a != str(root) else "." for a in argv]
    return " ".join(shown)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def run_tests(
    workspace_id: str,
    *,
    kind: str = "auto",
    target: str | None = None,
    timeout: int | None = None,
    prefer_pytest: bool | None = None,
    executor: str | None = None,
) -> dict[str, Any]:
    """Execute a workspace's tests inside its sandbox and summarise the result."""
    kind = kind or "auto"
    if kind not in KINDS:
        raise TestRunError(f"Unknown run kind {kind!r} (expected one of {', '.join(KINDS)})")

    executor_name = (executor or settings.CODE_EXECUTOR or "local").lower()
    if executor_name == "piston":
        # Optional remote executor (public Piston API). The public instance has
        # required an authorization token since Feb 2026 — set PISTON_API_KEY,
        # or stay on CODE_EXECUTOR=local (the default on Vercel). Dispatched
        # before any disk checks because the sandbox may live in the database.
        return _run_tests_piston(workspace_id, kind=kind, target=target, timeout=timeout)

    backend = os.getenv("DEVSTUDIO_BACKEND", settings.DEVSTUDIO_BACKEND).lower()
    tmp_root: Path | None = None
    if backend == "db":
        # Cloud/serverless mode: the sandbox tree lives in the database, but
        # execution needs real files. Materialise the tree into a temp dir and
        # run there — Vercel Functions allow subprocess with a writable /tmp,
        # so the bundled runner works unchanged in that environment.
        tmp_root = _materialize_db_sandbox(workspace_id)
        root = tmp_root
    else:
        root = devstudio.workspace_root(workspace_id)
        if not root.exists() or not any(root.iterdir()):
            raise TestRunError("The workspace sandbox is empty — seed the sample project first.")

    try:
        return _run_tests_in_root(
            root,
            workspace_id,
            kind=kind,
            target=target,
            timeout=timeout,
            prefer_pytest=prefer_pytest,
            executor=executor,
        )
    finally:
        if tmp_root is not None:
            shutil.rmtree(tmp_root, ignore_errors=True)


def _materialize_db_sandbox(workspace_id: str) -> Path:
    """Write the DB-backed sandbox tree into a fresh temp directory."""
    from app.core.database import SessionLocal
    from app.services.devstudio_store import get_store

    db = SessionLocal()
    try:
        files = get_store(db).get_all_files(workspace_id)
    finally:
        db.close()
    if not files:
        raise TestRunError("The workspace sandbox is empty — seed the sample project first.")
    root = Path(tempfile.mkdtemp(prefix=f"syncforge_ws_{uuid.uuid4().hex[:8]}_"))
    for f in files:
        dest = root / f["path"].replace("/", os.sep)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f.get("content") or "", encoding="utf-8")
    return root


def _run_tests_in_root(
    root: Path,
    workspace_id: str,
    *,
    kind: str = "auto",
    target: str | None = None,
    timeout: int | None = None,
    prefer_pytest: bool | None = None,
    executor: str | None = None,
) -> dict[str, Any]:
    """Execute a workspace's tests inside an on-disk sandbox root."""
    rel_target: str | None = None
    if target:
        try:
            rel_target = devstudio.normalize_rel(target)  # rejects traversal / .git
        except Exception as exc:  # noqa: BLE001
            raise TestRunError(str(exc)) from exc
        if not (root / rel_target).exists():
            raise TestRunError(f"{rel_target} was not found in the sandbox")

    resolved = kind if kind != "auto" else detect_kind(root, rel_target)
    if resolved is None:
        raise TestRunError(
            "Could not detect a test setup. Add a Python (test_*.py) or Node "
            "(node --test) test file, or run the bundled sample project."
        )

    prefer = settings.EXEC_PREFER_PYTEST if prefer_pytest is None else prefer_pytest
    executor_name = (executor or settings.CODE_EXECUTOR or "local").lower()
    notes: list[str] = []

    if executor_name not in ("local", "judge0"):
        notes.append(f"Unknown CODE_EXECUTOR {executor_name!r}; using the local runner.")
    elif executor_name == "judge0":
        notes.append(
            "CODE_EXECUTOR=judge0 is for single-file remote grading; project test "
            "runs execute in the local sandbox (no Docker/Judge0 required)."
        )

    runner = resolved
    argv: list[str]
    tmp_runner: Path | None = None

    if resolved == "python":
        if prefer and pytest_available():
            runner = "pytest"
            argv = [
                _interp(), "-m", "pytest", "-q", "--no-header", "--color=no",
                "-p", "no:cacheprovider", "-o", "addopts=",
            ]
            if rel_target:
                argv.append(rel_target)
        else:
            runner = "builtin"
            tmp_runner = Path(tempfile.gettempdir()) / f"syncforge_runner_{uuid.uuid4().hex}.py"
            tmp_runner.write_text(BUILTIN_RUNNER, encoding="utf-8")
            argv = [_interp(), str(tmp_runner), str(root), rel_target or ""]
    else:
        runner = "node"
        target_arg = rel_target or "."
        argv = ["node", "--test", target_arg]

    limit = _timeout(timeout)
    command = _display(argv, root)
    if notes:
        command += "   # " + " ".join(notes)

    try:
        proc, timed_out, duration = _run_process(argv, root=root, timeout=limit)
    finally:
        if tmp_runner is not None:
            try:
                tmp_runner.unlink(missing_ok=True)
            except OSError:  # pragma: no cover - best effort
                pass

    output = (proc.stdout or "") + (proc.stderr or "")
    exit_code = proc.returncode
    passed, failed, errors = parse_counts(output)

    if timed_out:
        status = TestRunStatus.TIMEOUT
        output = f"⏱️ Timed out after {limit}s.\n\n" + output
    elif has_no_tests(output):
        status = TestRunStatus.ERROR
        output = "No tests were collected.\n\n" + output
    elif failed or errors:
        status = TestRunStatus.FAILED
    elif exit_code == 0 and passed > 0:
        status = TestRunStatus.PASSED
    elif exit_code == 0:
        status = TestRunStatus.ERROR
        output = "No tests were collected.\n\n" + output
    else:
        status = TestRunStatus.ERROR

    if notes:
        output = "\n".join(f"ℹ️ {n}" for n in notes) + "\n\n" + output

    bounded, truncated = _truncate_output(output, settings.EXEC_MAX_OUTPUT_CHARS)

    if runner == "node" and exit_code is None and not errors:
        errors = 1 if status != TestRunStatus.PASSED else 0

    return {
        "kind": resolved,
        "runner": runner,
        "command": command[:1000],
        "target": rel_target,
        "status": status.value,
        "exit_code": exit_code,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "duration_ms": duration,
        "output": bounded,
        "output_truncated": truncated,
        "source": "local",
    }


def summarise(run: dict[str, Any]) -> str:
    """One-line human summary of a run result."""
    status = run.get("status")
    if status == TestRunStatus.PASSED.value:
        return f"All {run.get('passed', 0)} test(s) passed."
    if status == TestRunStatus.FAILED.value:
        return f"{run.get('failed', 0)} failed, {run.get('passed', 0)} passed."
    if status == TestRunStatus.TIMEOUT.value:
        return "The test run timed out."
    return "The test run could not be completed."
