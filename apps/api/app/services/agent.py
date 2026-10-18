"""Meeting→Code agent: turn decisions into a concrete engineering plan.

Given a meeting (its summary, decisions and action items) and the workspace's
sandbox file tree, this produces a plan with:

* **requirements** — what the meeting actually asked for,
* **subtasks** — concrete steps (code / test / docs / review),
* **affected_files** — the files most likely to need editing, with a reason,
* **proposed_changes** — `{path, instruction}` pairs ready to become the
  human-in-the-loop code proposals used by Dev Studio.

It reuses the same degradation ladder as the rest of SyncForge: an LLM
(``AGENT_MODEL``) when reachable, otherwise a deterministic offline planner that
scores files by keyword overlap. Offline output is labelled ``source="fallback"``
so the UI never pretends a model reasoned about it.

Nothing here writes code — it only plans.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from app.core.config import settings
from app.services import devstudio

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Offline planner
# --------------------------------------------------------------------------

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "had",
    "not", "but", "you", "your", "our", "their", "them", "they", "will", "would",
    "should", "could", "can", "may", "might", "must", "all", "any", "are", "was",
    "were", "been", "being", "into", "out", "over", "under", "about", "after",
    "before", "between", "than", "then", "there", "here", "when", "where", "which",
    "who", "whom", "what", "why", "how", "also", "just", "only", "very", "more",
    "most", "some", "such", "other", "each", "both", "few", "own", "same", "too",
    "use", "using", "used", "get", "got", "make", "made", "need", "needs", "want",
    "like", "well", "new", "one", "two", "let", "lets", "youre", "its", "it's",
    "kya", "hai", "hain", "kar", "karo", "karna", "ke", "ki", "ka", "ko", "mein",
    "me", "se", "par", "aur", "bhi", "nahi", "nahin", "tha", "thi", "the",
    "please", "pls", "ok", "okay", "yes", "no", "done", "next", "task", "tasks",
}

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_CAMEL_RE = re.compile(r"[a-z][A-Z]")
_DOC_EXTS = {".md", ".mdx", ".txt", ".rst"}


def _split_identifier(word: str) -> list[str]:
    """`divideByZero` / `divide_by_zero` → its lowercase parts."""
    parts = re.split(r"[_\W]+", word)
    expanded: list[str] = []
    for part in parts:
        if not part:
            continue
        # split camelCase as well
        chunks = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", part) or [part]
        expanded.extend(c.lower() for c in chunks)
    return expanded


def extract_keywords(texts: Iterable[str], limit: int = 40) -> list[str]:
    counts: dict[str, int] = {}
    for text in texts:
        if not text:
            continue
        for raw in _WORD_RE.findall(str(text)):
            for token in _split_identifier(raw):
                if len(token) < 3 or token in _STOPWORDS or token.isdigit():
                    continue
                counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _ in ranked[:limit]]


def _read_text(workspace_id: str, rel: str, db=None) -> str | None:
    return devstudio.read_content(workspace_id, rel, db=db)


def is_doc(path: str) -> bool:
    import os

    return os.path.splitext(path)[1].lower() in _DOC_EXTS


def is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return name.startswith("test") or name.endswith("_test.py") or "tests/" in path.lower()


def score_files(
    workspace_id: str,
    tree: dict[str, Any],
    keywords: list[str],
    max_files: int | None = None,
    db=None,
) -> list[dict[str, Any]]:
    """Rank sandbox files by keyword overlap with the meeting/decisions."""
    limit = max_files or settings.AGENT_MAX_FILES
    scored: list[dict[str, Any]] = []
    for rel in devstudio.flatten_paths(tree, 500):
        if not devstudio.is_editable(rel):
            continue
        content = _read_text(workspace_id, rel, db=db)
        path_l = rel.lower()
        content_l = (content or "").lower()
        hits: dict[str, int] = {}
        for kw in keywords:
            weight = 0
            if kw in path_l:
                weight += 3
            if content_l:
                weight += min(content_l.count(kw), 4)
            if weight:
                hits[kw] = weight
        score = sum(hits.values())
        if score <= 0:
            continue
        top = sorted(hits, key=lambda k: (-hits[k], k))[:4]
        scored.append({
            "path": rel,
            "score": score,
            "reason": "matches " + ", ".join(f"`{t}`" for t in top),
        })
    scored.sort(key=lambda item: (-item["score"], item["path"]))
    return scored[:limit]


def _dedupe(items: Iterable[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = (item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text[:300])
        if len(out) >= limit:
            break
    return out


def _offline_plan(
    workspace_id: str,
    *,
    tree: dict[str, Any],
    meeting: dict[str, Any] | None,
    decisions: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    focus: str | None,
    db=None,
) -> dict[str, Any]:
    meeting = meeting or {}
    corpus: list[str] = [meeting.get("title") or "", meeting.get("summary") or "", focus or ""]
    corpus += [str(p) for p in (meeting.get("key_points") or [])]
    corpus += [str(p) for p in (meeting.get("next_steps") or [])]
    for d in decisions:
        corpus += [d.get("title") or "", d.get("description") or "", d.get("rationale") or ""]
    for t in tasks:
        corpus += [t.get("title") or "", t.get("description") or ""]

    keywords = extract_keywords(corpus)
    affected = score_files(workspace_id, tree, keywords, db=db)

    requirements = _dedupe(
        [focus or ""]
        + [d.get("title") or "" for d in decisions]
        + [str(p) for p in (meeting.get("next_steps") or [])]
        + [str(p) for p in (meeting.get("key_points") or [])]
        + [t.get("title") or "" for t in tasks],
        limit=8,
    )
    if not requirements and meeting.get("title"):
        requirements = [f"Deliver the outcome of “{meeting['title']}”"]

    source_files = [a["path"] for a in affected if not is_test(a["path"]) and not is_doc(a["path"])]
    test_files = [a["path"] for a in affected if is_test(a["path"])]

    subtasks: list[dict[str, Any]] = []
    for path in source_files[:3]:
        subtasks.append({
            "title": f"Update `{path}` to satisfy the requirement",
            "kind": "code",
            "files": [path],
        })
    for path in (test_files[:2] or source_files[:1]):
        subtasks.append({
            "title": f"Add or update tests covering the change (`{path}`)",
            "kind": "test",
            "files": [path],
        })
    if affected:
        subtasks.append({
            "title": "Review the diff with a human before opening a pull request",
            "kind": "review",
            "files": [a["path"] for a in affected[:4]],
        })
    if not subtasks:
        subtasks.append({
            "title": "Create the module the change needs (the sandbox is empty)",
            "kind": "code",
            "files": [],
        })

    requirement_for_change = requirements[0] if requirements else "implement the meeting outcome"
    proposed_changes: list[dict[str, str]] = []
    for path in source_files[:3]:
        proposed_changes.append({"path": path, "instruction": requirement_for_change})

    n_decisions = len(decisions)
    title = f"Ship: {requirements[0]}" if requirements else "Code plan"
    summary = (
        f"Offline plan from {n_decisions} decision(s) in "
        f"“{meeting.get('title') or 'this meeting'}”. "
        f"Matched {len(affected)} file(s) by keyword overlap with the discussion."
    )

    return {
        "title": title[:500],
        "summary": summary,
        "requirements": requirements,
        "subtasks": subtasks,
        "affected_files": affected,
        "proposed_changes": proposed_changes,
        "keywords": keywords[:20],
        "source": "fallback",
    }


# --------------------------------------------------------------------------
# LLM planner (with automatic fallback)
# --------------------------------------------------------------------------

AGENT_SYSTEM = """You are SyncForge's Meeting→Code agent, a staff engineer who turns
meeting decisions into a concrete, minimal engineering plan for ONE repository.

Respond with ONLY valid JSON, no prose and no markdown fences:
{
  "title": "short imperative plan title",
  "summary": "2-3 sentences",
  "requirements": ["what the meeting asked for", "..."],
  "subtasks": [{"title": "...", "kind": "code|test|docs|review", "files": ["path"]}],
  "affected_files": [{"path": "existing/path", "reason": "why", "score": 0}],
  "proposed_changes": [{"path": "existing/path", "instruction": "what to change"}]
}

Rules:
- Only reference paths that appear in the provided file list. Never invent files.
- `affected_files` and `proposed_changes` should be the fewest files that could
  satisfy the requirements, with the most relevant first.
- `proposed_changes` are instructions for another agent, not diffs.
- Be concrete and terse. Support English and Hinglish.
"""


def _file_context(workspace_id: str, tree: dict[str, Any], db=None) -> str:
    lines: list[str] = []
    budget = settings.AGENT_CONTEXT_CHARS
    for rel in devstudio.flatten_paths(tree, 200):
        if not devstudio.is_editable(rel):
            continue
        head = _read_text(workspace_id, rel, db=db) or ""
        snippet = "\n".join(head.splitlines()[:40])[:600]
        block = f"### {rel}\n```\n{snippet}\n```\n"
        if budget - len(block) < 0:
            lines.append("… (file list truncated)")
            break
        budget -= len(block)
        lines.append(block)
    return "\n".join(lines) if lines else "(the workspace has no files)"


def _coerce_plan(raw: dict[str, Any], valid_paths: set[str], offline: dict[str, Any], db=None) -> dict[str, Any]:
    """Accept an LLM plan only where it is well-formed; otherwise keep offline parts."""

    def _paths(values: Any) -> list[str]:
        out: list[str] = []
        for value in values if isinstance(values, list) else []:
            if isinstance(value, str) and value in valid_paths and value not in out:
                out.append(value)
        return out

    title = raw.get("title")
    summary = raw.get("summary")

    requirements = _dedupe(
        [str(x) for x in raw.get("requirements", []) if isinstance(x, (str, int, float))],
        limit=10,
    ) or offline["requirements"]

    subtasks: list[dict[str, Any]] = []
    for item in raw.get("subtasks", []) if isinstance(raw.get("subtasks"), list) else []:
        if isinstance(item, str):
            subtasks.append({"title": item[:300], "kind": "code", "files": []})
        elif isinstance(item, dict) and item.get("title"):
            kind = str(item.get("kind") or "code").lower()
            if kind not in ("code", "test", "docs", "review"):
                kind = "code"
            subtasks.append({
                "title": str(item["title"])[:300],
                "kind": kind,
                "files": _paths(item.get("files")),
            })
    if not subtasks:
        subtasks = offline["subtasks"]

    affected: list[dict[str, Any]] = []
    for item in raw.get("affected_files", []) if isinstance(raw.get("affected_files"), list) else []:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if path not in valid_paths:
            continue
        try:
            score = int(item.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        affected.append({
            "path": path,
            "score": score,
            "reason": str(item.get("reason") or "referenced by the plan")[:300],
        })
    if not affected:
        affected = offline["affected_files"]
    affected = affected[: settings.AGENT_MAX_FILES]

    proposed: list[dict[str, str]] = []
    for item in raw.get("proposed_changes", []) if isinstance(raw.get("proposed_changes"), list) else []:
        if isinstance(item, dict) and item.get("path") in valid_paths and item.get("instruction"):
            proposed.append({
                "path": item["path"],
                "instruction": str(item["instruction"])[:2000],
            })
    if not proposed:
        proposed = offline["proposed_changes"]

    return {
        "title": (str(title).strip() if title else offline["title"])[:500],
        "summary": str(summary).strip() if summary else offline["summary"],
        "requirements": requirements,
        "subtasks": subtasks,
        "affected_files": affected,
        "proposed_changes": proposed,
        "keywords": offline.get("keywords", []),
        "source": "llm",
    }


def ai_code_plan(
    workspace_id: str,
    *,
    tree: dict[str, Any],
    meeting: dict[str, Any] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    focus: str | None = None,
    allow_fallback: bool | None = None,
    db=None,
) -> dict[str, Any]:
    """Build a Meeting→Code plan. Always returns a dict with a ``source`` key."""
    decisions = decisions or []
    tasks = tasks or []
    if allow_fallback is None:
        allow_fallback = settings.ALLOW_EXTRACTIVE_FALLBACK

    offline = _offline_plan(
        workspace_id, tree=tree, meeting=meeting, decisions=decisions, tasks=tasks, focus=focus, db=db
    )
    valid_paths = set(devstudio.flatten_paths(tree, 500))

    meeting = meeting or {}
    decision_lines = "\n".join(
        f"- {d.get('title')} ({d.get('impact', 'medium')})"
        + (f": {d.get('description')}" if d.get("description") else "")
        for d in decisions
    ) or "(none recorded)"
    task_lines = "\n".join(
        f"- {t.get('title')} [{t.get('status', 'todo')}]" for t in tasks
    ) or "(none)"
    user = (
        f"## Meeting\nTitle: {meeting.get('title') or '(untitled)'}\n"
        f"Summary: {meeting.get('summary') or '(none)'}\n"
        f"Key points: {'; '.join(str(p) for p in (meeting.get('key_points') or [])) or '(none)'}\n"
        f"Next steps: {'; '.join(str(p) for p in (meeting.get('next_steps') or [])) or '(none)'}\n\n"
        f"## Decisions\n{decision_lines}\n\n"
        f"## Linked tasks\n{task_lines}\n\n"
        f"## Extra focus from the user\n{focus or '(none)'}\n\n"
        f"## Repository files (only these exist)\n{_file_context(workspace_id, tree, db=db)}\n\n"
        "Produce the plan JSON now."
    )

    try:
        from app.services.llm import structured_completion

        raw = structured_completion(
            system=AGENT_SYSTEM,
            user=user,
            model=settings.AGENT_MODEL,
            temperature=0.2,
            max_tokens=4096,
        )
        if not isinstance(raw, dict):
            raise ValueError("plan was not a JSON object")
        return _coerce_plan(raw, valid_paths, offline, db=db)
    except Exception as exc:
        if not allow_fallback:
            raise
        logger.warning("Meeting→Code agent LLM unavailable (%s); using offline planner", exc)
        offline["fallback_reason"] = str(exc)[:300]
        return offline
