"""Live Phase 5 verification against a running API (real HTTP, no TestClient).

Covers the "verify" and "remember" pipelines over real HTTP: sandboxed test
runs (the bundled offline runner, fail → fix → pass) and Project Memory
(index → search → clear).

Usage (from apps/api):  python tests/verify_live_phase5.py [base_url]
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
    email = f"p5+{name.lower()}+{uuid.uuid4().hex[:6]}@example.com"
    r = c.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "name": name},
    )
    r.raise_for_status()
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


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as c:
        owner_h = register(c, "VerifyOwner")[1]
        stray_h = register(c, "VerifyStray")[1]

        r = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Phase5 Verify WS"})
        check("create workspace", r.status_code == 201, r.json().get("slug", ""))
        ws = r.json()["id"]

        studio = f"/api/v1/workspaces/{ws}/studio"
        tests = f"/api/v1/workspaces/{ws}/tests"
        memory = f"/api/v1/workspaces/{ws}/memory"

        # ------------------------------------------------------- verify: tests
        r = c.post(f"{studio}/seed", headers=owner_h)
        check("studio: sample seeded", r.status_code == 201, "")

        r = c.post(f"{tests}/run", headers=owner_h, json={})
        body = r.json()
        check(
            "verify: run reports the failing divide test",
            r.status_code == 201
            and body["status"] == "failed"
            and body["passed"] == 4
            and body["failed"] == 1,
            f"{body.get('passed')}/{body.get('failed')}",
        )
        check(
            "verify: bundled offline runner used",
            body["runner"] in ("builtin", "pytest") and body["source"] == "local",
            body["runner"],
        )

        r = c.get(f"{tests}/latest", headers=owner_h)
        check("verify: latest run", r.status_code == 200, r.json().get("status", ""))

        # ----------------------------------------------------- memory: RAG
        # Indexed while the seeded calculator.py still carries its
        # "# TODO: guard against division by zero" comment, so the query
        # "divide by zero guard" ranks the source file first.
        r = c.post(f"{memory}/index", headers=owner_h, json={})
        body = r.json()
        check(
            "memory: index builds chunks",
            r.status_code == 200 and body["created"] > 0 and body["chunks"] >= 4,
            f"created={body.get('created')} chunks={body.get('chunks')}",
        )
        check(
            "memory: offline embedder reported",
            body["source"] == "fallback" and body["dim"] > 0,
            f"{body.get('source')} dim={body.get('dim')}",
        )

        r = c.post(f"{memory}/index", headers=owner_h, json={})
        again = r.json()
        check(
            "memory: re-index is idempotent",
            again["created"] == 0 and again["skipped"] > 0,
            f"created={again.get('created')} skipped={again.get('skipped')}",
        )

        r = c.get(f"{memory}/stats", headers=owner_h)
        stats = r.json()
        check(
            "memory: stats reflect the index",
            stats["chunks"] >= 4 and "file" in stats["by_type"],
            f"chunks={stats.get('chunks')} by_type={stats.get('by_type')}",
        )

        r = c.post(
            f"{memory}/search",
            headers=owner_h,
            json={"query": "divide by zero guard", "k": 3},
        )
        hits = r.json()
        check(
            "memory: search returns ranked hits",
            r.status_code == 200 and hits["count"] > 0,
            f"count={hits.get('count')}",
        )
        if hits["results"]:
            top = hits["results"][0]
            check(
                "memory: calculator file ranks first",
                top["source_id"].endswith("calculator.py"),
                f"{top['score']} {top['source_id']}",
            )
        check(
            "memory: offline source labelled on search",
            hits["source"] == "fallback",
            hits["source"],
        )

        r = c.post(f"{memory}/search", headers=owner_h, json={"query": "   "})
        check("memory: blank query rejected", r.status_code == 400, f"status={r.status_code}")

        r = c.delete(f"{memory}", headers=owner_h)
        check(
            "memory: clear empties the index",
            r.status_code == 200 and r.json()["removed"] >= 4,
            f"removed={r.json().get('removed') if r.status_code == 200 else '?'}",
        )
        r = c.get(f"{memory}/stats", headers=owner_h)
        check("memory: stats empty after clear", r.json()["chunks"] == 0, f"chunks={r.json()['chunks']}")

        # ---------------------------------------------------------- permissions
        r = c.post(f"{tests}/run", headers=stray_h, json={})
        check("verify: non-member blocked", r.status_code == 403, f"status={r.status_code}")
        r = c.post(f"{memory}/search", headers=stray_h, json={"query": "x"})
        check("memory: non-member blocked", r.status_code == 403, f"status={r.status_code}")

        # human applies the fix → all green (after memory checks, since the fix
        # replaces the TODO comment the search above relied on)
        r = c.put(
            f"{studio}/files/src/calculator.py",
            headers=owner_h,
            json={"content": FIXED_CALCULATOR},
        )
        check("verify: fix written by a human", r.status_code == 200, f"status={r.status_code}")

        r = c.post(f"{tests}/run", headers=owner_h, json={})
        body = r.json()
        check(
            "verify: all green after the fix",
            r.status_code == 201
            and body["status"] == "passed"
            and body["failed"] == 0
            and body["passed"] == 5,
            f"{body.get('passed')}/{body.get('failed')}",
        )

        r = c.get(tests, headers=owner_h)
        check("verify: run history", r.status_code == 200 and len(r.json()) >= 2, f"n={len(r.json())}")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
