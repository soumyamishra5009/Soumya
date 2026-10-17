"""Run every API test suite as a subprocess and report a combined summary.

Usage (from apps/api):  python tests/run_all.py
"""

from __future__ import annotations

import os
import subprocess
import sys

TESTS = [
    "tests/test_smoke.py",
    "tests/test_normalize.py",
    "tests/test_llm_providers.py",
    "tests/test_fallback.py",
    "tests/test_pipeline.py",
    "tests/test_fallback_pipeline.py",
    "tests/test_team.py",
    "tests/test_studio.py",
    "tests/test_ship.py",
    "tests/test_verify.py",
    "tests/test_memory.py",
]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    api_root = os.path.dirname(here)
    python = sys.executable

    results: list[tuple[str, int, str]] = []

    for name in TESTS:
        print("=" * 70)
        print(f"RUN  {name}")
        print("=" * 70)
        proc = subprocess.run(
            [python, os.path.join(here, os.path.basename(name))],
            cwd=api_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        # Print only the meaningful lines (PASS/FAIL/summary/errors)
        for line in out.splitlines():
            stripped = line.strip()
            if (
                stripped.startswith(("PASS", "FAIL"))
                or "passed" in stripped
                or stripped.startswith("FAILED")
                or "Traceback" in stripped
                or stripped.startswith("AssertionError")
            ):
                print(stripped)
        results.append((name, proc.returncode, out))
        print()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ok = True
    for name, code, _ in results:
        status = "OK " if code == 0 else "ERR"
        if code != 0:
            ok = False
        print(f"{status} {name}  (exit={code})")

    print("\nALL TESTS PASSED" if ok else "\nSOME TESTS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
