"""Phase 5 tests: Project Memory (workspace RAG).

Covers the deterministic offline embedder (no model required), chunking,
indexing/idempotency/stale removal, ranked search, the HTTP surface and the
permission model.

Run from apps/api:  python tests/test_memory.py
"""

from __future__ import annotations

import math
import os
import shutil
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = os.path.join(tempfile.gettempdir(), f"test_memory_{uuid.uuid4().hex}.db")
SANDBOX = os.path.join(tempfile.gettempdir(), f"memory_{uuid.uuid4().hex}")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.replace(os.sep, '/')}"
os.environ["DEVSTUDIO_ROOT"] = SANDBOX.replace(os.sep, "/")
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["GITHUB_TOKEN"] = ""
os.environ["ALLOW_EXTRACTIVE_FALLBACK"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services import devstudio, memory  # noqa: E402

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


def norm(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


def run() -> int:
    from app.core.database import init_db

    init_db()
    c = TestClient(main.app)

    # ------------------------------------------------------- unit: tokenising
    tokens = memory.tokenize("def divideByZero / rate_limit ONE_MINUS")
    check(
        "tokenize: camel + snake + lower",
        "divide" in tokens and "zero" in tokens and "rate" in tokens
        and "limit" in tokens and all(t.islower() for t in tokens),
        str(tokens),
    )
    check("tokenize: short tokens dropped", "a" not in memory.tokenize("a b c"), "")

    # ---------------------------------------------------------- unit: embedder
    dim = settings.MEMORY_EMBED_DIM
    a = memory.hash_embed("divide by zero handling", dim)
    b = memory.hash_embed("divide by zero handling", dim)
    check("embed: deterministic", a == b, "")
    check("embed: correct dimension", len(a) == dim, f"len={len(a)}")
    check("embed: L2 normalised", abs(norm(a) - 1.0) < 1e-3, f"norm={norm(a):.4f}")
    empty = memory.hash_embed("   ", dim)
    check("embed: blank -> zero vector", norm(empty) == 0.0, f"norm={norm(empty)}")

    calculator = memory.hash_embed(
        "def divide(a, b):\n    if b == 0:\n        return None\n    return a / b", dim
    )
    readme = memory.hash_embed("SyncForge AI monorepo readme setup instructions", dim)
    query = memory.hash_embed("divide by zero guard", dim)
    check(
        "cosine: related ranks above unrelated",
        memory.cosine(query, calculator) > memory.cosine(query, readme),
        f"{memory.cosine(query, calculator):.3f} > {memory.cosine(query, readme):.3f}",
    )
    check("cosine: identical -> 1", abs(memory.cosine(a, b) - 1.0) < 1e-6, "")
    check("cosine: zero guard -> 0", memory.cosine(empty, a) == 0.0, "")
    check("cosine: length mismatch -> 0", memory.cosine(a, a[:10]) == 0.0, "")

    # ----------------------------------------------------------- unit: chunking
    check("chunk: short text stays whole", len(memory.chunk_text("hello world")) == 1, "")
    check("chunk: blank -> none", memory.chunk_text("") == [], "")
    big = "\n".join(f"line {i} of the meeting transcript about shipping" for i in range(200))
    chunks = memory.chunk_text(big, 400, 50)
    check("chunk: splits long text", len(chunks) > 1, f"n={len(chunks)}")
    check(
        "chunk: every chunk within size",
        all(len(x) <= 400 for x in chunks),
        f"max={max((len(x) for x in chunks), default=0)}",
    )
    joined_words = set(" ".join(" ".join(chunks).split()).split())
    original_words = set(" ".join(big.split()).split())
    check("chunk: no content lost",
          original_words <= joined_words,
          f"missing={len(original_words - joined_words)}")

    # ------------------------------------------------------------- HTTP setup
    owner_email, owner_h = register(c, "MemoryOwner")
    member_email, member_h = register(c, "MemoryMember")
    stray_h = register(c, "MemoryStray")[1]

    ws = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Memory WS"}).json()["id"]
    c.post(
        f"/api/v1/workspaces/{ws}/members", headers=owner_h,
        json={"email": member_email, "role": "member"},
    )
    base = f"/api/v1/workspaces/{ws}"
    studio = f"{base}/studio"

    # ------------------------------------------------------------ empty states
    r = c.get(f"{base}/memory/stats", headers=owner_h)
    check("stats: empty workspace", r.status_code == 200 and r.json()["chunks"] == 0, "")
    r = c.post(f"{base}/memory/search", headers=owner_h, json={"query": "anything"})
    check(
        "search: before indexing -> hint",
        r.status_code == 200 and r.json()["indexed"] == 0 and bool(r.json()["message"]),
        r.json().get("message", "")[:50],
    )
    r = c.post(f"{base}/memory/search", headers=owner_h, json={"query": "   "})
    check("search: blank query -> 400", r.status_code == 400, f"status={r.status_code}")

    # --------------------------------------------------------------- first index
    r = c.post(f"{studio}/seed", headers=owner_h)
    check("studio: sample seeded", r.status_code == 201, "")
    r = c.post(f"{base}/memory/index", headers=owner_h, json={})
    body = r.json()
    check("index: 200 with counts", r.status_code == 200, f"status={r.status_code}")
    check(
        "index: seeded sandbox chunks created",
        body["created"] > 0 and body["chunks"] >= 4,
        f"created={body['created']} total={body['chunks']}",
    )
    check(
        "index: offline embedder reported",
        body["source"] == "fallback" and body["dim"] == dim,
        f"{body['source']} dim={body['dim']}",
    )
    check("index: message present", bool(body["message"]), body["message"][:60])
    file_chunks = body["by_type"].get("file", 0)
    check("index: sandbox files indexed", file_chunks >= 4, f"files={file_chunks}")

    # ------------------------------------------------------------ idempotency
    r2 = c.post(f"{base}/memory/index", headers=owner_h, json={})
    again = r2.json()
    check(
        "index: second run skips unchanged",
        again["created"] == 0 and again["skipped"] > 0 and again["skipped"] == again["chunks"],
        f"created={again['created']} skipped={again['skipped']} chunks={again['chunks']}",
    )
    check("index: nothing stale yet", again["removed"] == 0, str(again["removed"]))
    forced = c.post(f"{base}/memory/index", headers=owner_h, json={"force": True}).json()
    check(
        "index: force re-embeds everything",
        forced["created"] == 0 and forced["indexed"] == forced["chunks"],
        f"indexed={forced['indexed']} chunks={forced['chunks']}",
    )

    # ------------------------------------------------------------------- search
    r = c.post(
        f"{base}/memory/search", headers=owner_h,
        json={"query": "divide by zero guard", "k": 3},
    )
    hits = r.json()
    check("search: 200 with results", r.status_code == 200 and hits["count"] > 0, f"n={hits['count']}")
    top = hits["results"][0]
    check(
        "search: calculator file ranks first",
        top["source_id"].endswith("calculator.py"),
        f"{top['score']} {top['source_id']}",
    )
    check(
        "search: results sorted by score",
        all(
            hits["results"][i]["score"] >= hits["results"][i + 1]["score"]
            for i in range(len(hits["results"]) - 1)
        ),
        "",
    )
    check("search: scores exposed", all(h["score"] > 0 for h in hits["results"]), "")
    check("search: snippet included", bool(top["snippet"]), top["snippet"][:40])
    check("search: offline source labelled", hits["source"] == "fallback", hits["source"])
    check("search: min_score surfaced", "min_score" in hits, str(hits.get("min_score")))

    one = c.post(f"{base}/memory/search", headers=owner_h,
                 json={"query": "divide by zero", "k": 1}).json()
    check("search: k respected", one["count"] <= 1, f"count={one['count']}")
    typed = c.post(f"{base}/memory/search", headers=owner_h,
                   json={"query": "divide by zero", "types": ["file"]}).json()
    check(
        "search: type filter respected",
        typed["count"] > 0 and all(h["source_type"] == "file" for h in typed["results"]),
        f"n={typed['count']}",
    )
    ignored = c.post(f"{base}/memory/search", headers=owner_h,
                     json={"query": "divide by zero", "types": ["nonsense"]}).json()
    check(
        "search: unknown type ignored",
        ignored["count"] == 0 or all(h["source_type"] in {"file", "meeting", "decision", "task", "note"}
                                     for h in ignored["results"]),
        f"n={ignored['count']}",
    )

    # -------------------------------------------- meetings, decisions and tasks
    meeting = c.post(
        "/api/v1/meetings", headers=owner_h,
        json={
            "workspace_id": ws,
            "title": "Sprint 4 planning",
            "description": "Roadmap sync for the billing team",
        },
    ).json()
    mid = meeting["id"]
    c.patch(
        f"/api/v1/meetings/{mid}", headers=owner_h,
        json={
            "summary": "The team agreed to ship the billing v2 rollout behind a feature flag before the launch event.",
            "key_points": ["Billing v2 rollout must ship first", "Feature flag gates the rollout"],
            "next_steps": ["Create the billing feature flag", "Draft the migration plan"],
        },
    )
    decision = c.post(
        f"/api/v1/meetings/{mid}/decisions", headers=owner_h,
        json={
            "title": "Use a feature flag for billing v2",
            "description": "Roll out billing v2 gradually instead of a big bang release.",
            "impact": "high",
            "rationale": "Keeps the launch event safe if pricing regressions appear.",
        },
    ).json()
    dec_id = decision["id"]
    c.post(
        "/api/v1/tasks", headers=owner_h,
        json={
            "workspace_id": ws,
            "title": "Create the billing feature flag",
            "description": "Add FLAG_BILLING_V2 and default it to off in production.",
            "priority": "high",
        },
    )

    r = c.post(f"{base}/memory/index", headers=owner_h, json={})
    added = r.json()
    check("index: meetings + decisions + tasks added",
          added["by_type"].get("meeting", 0) > 0 and added["by_type"].get("decision", 0) > 0
          and added["by_type"].get("task", 0) > 0,
          str(added["by_type"]))
    check("index: chunk total grew", added["chunks"] > file_chunks, f"{added['chunks']} > {file_chunks}")

    stats = c.get(f"{base}/memory/stats", headers=owner_h).json()
    check("stats: reflects every source",
          stats["chunks"] == added["chunks"] and stats["by_type"].get("decision", 0) > 0,
          str(stats["by_type"]))
    check("stats: embed sources recorded",
          stats["embed_sources"] == ["fallback"] and stats["dims"] == [dim],
          f"{stats['embed_sources']} {stats['dims']}")

    # Delete a source and confirm its chunks are dropped as stale.
    before_delete = stats["chunks"]
    r = c.delete(f"/api/v1/decisions/{dec_id}", headers=owner_h)
    check("decision: deleted", r.status_code == 204, f"status={r.status_code}")
    r = c.post(f"{base}/memory/index", headers=owner_h, json={})
    rebuilt = r.json()
    check(
        "index: stale chunks removed after source deleted",
        rebuilt["removed"] >= 1 and rebuilt["chunks"] == before_delete - 1,
        f"removed={rebuilt['removed']} {before_delete} -> {rebuilt['chunks']}",
    )
    still_files = rebuilt["by_type"].get("file", 0)
    check("index: files still indexed", still_files >= 4, f"files={still_files}")

    # ------------------------------------------------------- include_code off
    no_code = c.post(f"{base}/memory/index", headers=owner_h,
                     json={"include_code": False, "force": True}).json()
    check(
        "index: include_code=False drops file chunks",
        no_code["by_type"].get("file", 0) == 0 and no_code["removed"] > 0,
        str(no_code["by_type"]),
    )
    # Put code back so the chunks-list section below has file chunks to work with.
    restored = c.post(f"{base}/memory/index", headers=owner_h, json={"include_code": True}).json()
    check("index: code re-indexed after opt-out",
          restored["by_type"].get("file", 0) >= 4 and restored["created"] >= 4,
          f"files={restored['by_type'].get('file', 0)} created={restored['created']}")

    # ------------------------------------------------------------- permissions
    r = c.post(f"{base}/memory/index", headers=stray_h, json={})
    check("permissions: non-member index -> 403", r.status_code == 403, f"status={r.status_code}")
    r = c.post(f"{base}/memory/search", headers=stray_h, json={"query": "anything"})
    check("permissions: non-member search -> 403", r.status_code == 403, f"status={r.status_code}")
    r = c.post(f"{base}/memory/search", headers=member_h, json={"query": "rollout"})
    check("permissions: member may search", r.status_code == 200, f"status={r.status_code}")

    # ------------------------------------------------- chunks list + deletion
    r = c.get(f"{base}/memory/chunks", headers=owner_h)
    chunks_list = r.json()
    check("chunks: listable", r.status_code == 200 and len(chunks_list) > 0, f"n={len(chunks_list)}")
    typed_list = c.get(f"{base}/memory/chunks?type=file", headers=owner_h).json()
    check(
        "chunks: type filter works",
        len(typed_list) > 0 and all(x["source_type"] == "file" for x in typed_list),
        f"n={len(typed_list)}",
    )
    victim = next(x for x in typed_list)
    total_before = c.get(f"{base}/memory/stats", headers=owner_h).json()["chunks"]
    r = c.delete(f"{base}/memory/chunks/{victim['id']}", headers=owner_h)
    check("chunks: single chunk deleted", r.status_code == 204, f"status={r.status_code}")
    total_after = c.get(f"{base}/memory/stats", headers=owner_h).json()["chunks"]
    check("chunks: count decremented", total_after == total_before - 1,
          f"{total_before} -> {total_after}")
    r = c.delete(f"{base}/memory/chunks/{uuid.uuid4()}", headers=owner_h)
    check("chunks: unknown id -> 404", r.status_code == 404, f"status={r.status_code}")

    # -------------------------------------------------------------- workspace isolation
    ws2 = c.post("/api/v1/workspaces", headers=owner_h, json={"name": "Other WS"}).json()["id"]
    base2 = f"/api/v1/workspaces/{ws2}"
    stats2 = c.get(f"{base2}/memory/stats", headers=owner_h).json()
    check("isolation: second workspace is empty", stats2["chunks"] == 0, str(stats2["chunks"]))

    # --------------------------------------------------------------- clear
    r = c.delete(f"{base}/memory", headers=owner_h)
    cleared = r.json()
    check("clear: removes everything", r.status_code == 200 and cleared["removed"] > 0,
          f"removed={cleared['removed']}")
    check("clear: stats now empty",
          c.get(f"{base}/memory/stats", headers=owner_h).json()["chunks"] == 0, "")
    check("clear: message present", bool(cleared["message"]), cleared["message"][:50])

    c.post(f"{base}/memory/index", headers=owner_h, json={})
    remaining = c.get(f"{base}/memory/stats", headers=owner_h).json()["chunks"]
    r = c.delete(f"{base}/memory?type=file", headers=owner_h)
    check("clear: type filter works", r.status_code == 200 and r.json()["removed"] > 0,
          f"removed={r.json()['removed']}")
    after_partial = c.get(f"{base}/memory/stats", headers=owner_h).json()["chunks"]
    check("clear: other types survive",
          0 < after_partial < remaining,
          f"{remaining} -> {after_partial}")
    r = c.delete(f"{base}/memory?type=bogus", headers=owner_h)
    check("clear: unknown type -> 400", r.status_code == 400, f"status={r.status_code}")

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
