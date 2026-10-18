"""Dev Studio: a sandboxed, per-workspace code tree plus AI assistance.

Two responsibilities:

1. **Sandbox** — a small virtual file system rooted at
   ``settings.DEVSTUDIO_ROOT/<workspace_id>``. Every path is normalised and
   verified to stay inside that root, so a workspace can never read or write
   files elsewhere on the host. Only text/code files are editable.

2. **AI assistance** — context-aware chat and *proposed* code changes. When no
   LLM is reachable the module degrades to a deterministic, offline analyser
   (structure overview, TODO scan, a small static linter, scaffolding
   proposals). Offline output is always labelled ``source="fallback"`` so the
   UI can be honest about it — the same degradation ladder used by the meeting
   summarizer.

Nothing here writes code on its own: :func:`ai_code_proposal` only *returns*
suggested contents. Persisting them is an explicit, human-approved action in
the API layer.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable

from app.core.config import settings

logger = logging.getLogger(__name__)


def _store(db=None):
    """Return the active storage backend (disk or db)."""
    from app.services.devstudio_store import get_store

    return get_store(db)


def read_content(workspace_id: str, rel_path: str, db=None) -> str | None:
    """Read raw file content via the active store (used by agent/testrunner)."""
    return _store(db).read_content(workspace_id, rel_path)

# --------------------------------------------------------------------------
# Paths, extensions and limits
# --------------------------------------------------------------------------

# Files that are editable even though they have no (or a dotted) extension.
ALLOWED_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "Procfile",
    "LICENSE",
    "NOTICE",
    "CHANGELOG",
    "README",
    ".gitignore",
    ".dockerignore",
    ".editorconfig",
    ".env.example",
    ".env.sample",
}

ALLOWED_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".json", ".jsonc", ".md", ".mdx", ".txt", ".rst", ".csv",
    ".css", ".scss", ".sass", ".less", ".html", ".htm", ".xml", ".svg",
    ".sql", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".properties",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".java", ".go", ".rs", ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".cs", ".kt", ".kts", ".swift", ".r", ".lua", ".pl", ".dart",
    ".vue", ".svelte", ".graphql", ".gql", ".proto", ".tf", ".gradle",
}

LANG_BY_EXT = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".json": "json", ".jsonc": "json",
    ".md": "markdown", ".mdx": "markdown", ".txt": "plaintext", ".rst": "plaintext",
    ".css": "css", ".scss": "scss", ".sass": "scss", ".less": "less",
    ".html": "html", ".htm": "html", ".xml": "xml", ".svg": "xml",
    ".sql": "sql", ".yml": "yaml", ".yaml": "yaml", ".toml": "ini", ".ini": "ini",
    ".cfg": "ini", ".conf": "ini", ".properties": "ini",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".ps1": "powershell", ".bat": "bat", ".cmd": "bat",
    ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift",
    ".r": "r", ".lua": "lua", ".pl": "perl", ".dart": "dart",
    ".vue": "html", ".svelte": "html", ".graphql": "graphql", ".gql": "graphql",
    ".proto": "protobuf", ".tf": "hcl", ".gradle": "groovy", ".csv": "plaintext",
}

_SPECIAL_LANG = {"Dockerfile": "dockerfile", "Makefile": "makefile"}

COMMENT_PREFIX = {
    "python": "#", "shell": "#", "powershell": "#", "yaml": "#", "ini": "#",
    "ruby": "#", "r": "#", "perl": "#", "dockerfile": "#", "makefile": "#",
    "javascript": "//", "typescript": "//", "java": "//", "go": "//", "rust": "//",
    "c": "//", "cpp": "//", "csharp": "//", "kotlin": "//", "swift": "//",
    "php": "//", "dart": "//", "groovy": "//", "protobuf": "//", "hcl": "#",
    "sql": "--", "lua": "--", "html": "<!--", "css": "/*", "scss": "/*",
    "less": "/*", "markdown": "<!--", "graphql": "#",
}

def max_file_bytes() -> int:
    return settings.DEVSTUDIO_MAX_FILE_KB * 1024

# Binary-ish files are never read into the editor.
_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".pdf", ".zip",
    ".gz", ".tar", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".pyc", ".pyo", ".class", ".jar", ".o", ".a", ".db", ".sqlite", ".woff",
    ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".wav", ".webm", ".mov",
}


class SandboxError(ValueError):
    """Raised for invalid paths or disallowed operations inside the sandbox."""


# --------------------------------------------------------------------------
# Sandbox primitives
# --------------------------------------------------------------------------


def workspace_root(workspace_id: str) -> Path:
    """Absolute sandbox directory for a workspace (not necessarily existing)."""
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", workspace_id or "")
    if not safe_id:
        raise SandboxError("Invalid workspace id")
    return (Path(settings.DEVSTUDIO_ROOT).resolve() / safe_id)


def normalize_rel(rel_path: str) -> str:
    """Validate and canonicalise a sandbox-relative POSIX path.

    Rejects absolute paths, drive letters, NUL bytes, ``..`` segments and
    anything that resolves outside the workspace root.
    """
    raw = (rel_path or "").strip().replace("\\", "/")
    if not raw or raw in (".", "/", "./"):
        raise SandboxError("A file path is required")
    if "\x00" in raw:
        raise SandboxError("Invalid path")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or raw.startswith("~"):
        raise SandboxError("Absolute paths are not allowed")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise SandboxError("Path traversal is not allowed")
    # The git metadata directory is managed by the app, never through the file
    # API — otherwise a delete could nuke the workspace's repository.
    if any(p == ".git" for p in parts):
        raise SandboxError("The .git directory is managed automatically")
    if not parts:
        raise SandboxError("A file path is required")
    return "/".join(parts)


def resolve_path(workspace_id: str, rel_path: str) -> tuple[Path, str]:
    """Return ``(absolute_path, normalised_rel_path)`` inside the sandbox."""
    rel = normalize_rel(rel_path)
    root = workspace_root(workspace_id)
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and not candidate.is_relative_to(root_resolved):
        raise SandboxError("Path escapes the workspace sandbox")
    return candidate, rel


def language_for(rel_path: str) -> str:
    name = Path(rel_path).name
    if name in _SPECIAL_LANG:
        return _SPECIAL_LANG[name]
    return LANG_BY_EXT.get(Path(name).suffix.lower(), "plaintext")


def is_editable(rel_path: str) -> bool:
    """True when the file is a text/code file the studio is allowed to edit."""
    name = Path(rel_path).name
    if name in ALLOWED_FILENAMES:
        return True
    if name.startswith("."):
        return False
    ext = Path(name).suffix.lower()
    if ext in _BINARY_EXTS:
        return False
    return ext in ALLOWED_EXTS


def content_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def diff_stats(original: str | None, proposed: str | None) -> tuple[int, int]:
    """Return ``(added_lines, removed_lines)`` between two texts."""
    a = (original or "").splitlines()
    b = (proposed or "").splitlines()
    matcher = difflib.SequenceMatcher(None, a, b)
    added = removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return added, removed


# --------------------------------------------------------------------------
# Tree / read / write / create / delete
# --------------------------------------------------------------------------


def _entry_node(path: Path, rel: str) -> dict[str, Any]:
    return {
        "name": path.name,
        "path": rel,
        "type": "file",
        "size": path.stat().st_size,
        "language": language_for(rel),
        "editable": is_editable(rel),
    }


def _build_dir(
    path: Path,
    rel: str,
    depth: int,
    counter: list[int],
    truncated: list[bool],
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "name": path.name,
        "path": rel,
        "type": "dir",
        "children": [],
    }
    if depth >= settings.DEVSTUDIO_MAX_DEPTH:
        if path.exists() and any(path.iterdir()):
            truncated[0] = True
        return node

    try:
        entries = sorted(
            path.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except OSError:
        return node

    for entry in entries:
        if counter[0] >= settings.DEVSTUDIO_MAX_FILES:
            truncated[0] = True
            break
        if entry.name.startswith(".") and entry.name not in ALLOWED_FILENAMES:
            continue
        child_rel = f"{rel}/{entry.name}" if rel else entry.name
        try:
            if entry.is_dir():
                node["children"].append(
                    _build_dir(entry, child_rel, depth + 1, counter, truncated)
                )
            elif entry.is_file():
                node["children"].append(_entry_node(entry, child_rel))
                counter[0] += 1
        except OSError:  # pragma: no cover - unreadable entry
            continue
    return node


def list_tree(workspace_id: str, db=None) -> dict[str, Any]:
    """Nested tree of the workspace sandbox (dirs first, then files)."""
    return _store(db).list_tree(workspace_id)


def read_file(workspace_id: str, rel_path: str, db=None) -> dict[str, Any]:
    """Read a text file from the sandbox."""
    return _store(db).read_file(workspace_id, rel_path)


def write_file(workspace_id: str, rel_path: str, content: str, db=None) -> dict[str, Any]:
    """Create or overwrite a text file (parent directories are created)."""
    return _store(db).write_file(workspace_id, rel_path, content)


def create_file(workspace_id: str, rel_path: str, content: str = "", db=None) -> dict[str, Any]:
    """Create a new file, refusing to clobber an existing one."""
    return _store(db).create_file(workspace_id, rel_path, content)


def create_dir(workspace_id: str, rel_path: str, db=None) -> dict[str, Any]:
    return _store(db).create_dir(workspace_id, rel_path)


def delete_entry(workspace_id: str, rel_path: str, db=None) -> dict[str, Any]:
    """Delete a file or a directory (recursively). Never the sandbox root."""
    return _store(db).delete_entry(workspace_id, rel_path)


def _mtime(path: Path) -> str:
    from datetime import datetime, timezone

    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:  # pragma: no cover
        return ""


# --------------------------------------------------------------------------
# Sample project (so the studio is useful out of the box)
# --------------------------------------------------------------------------

SAMPLE_FILES: dict[str, str] = {
    "README.md": """# Sample project

This project exists so you can try the full **Meeting → Decision → Task → Code
→ Verification** loop inside SyncForge Dev Studio.

`src/calculator.py` has three deliberate problems:

1. `divide()` has no division-by-zero guard.
2. `is_zero()` uses `== None` instead of `is None`.
3. `average()` uses a mutable default argument.

`tests/test_calculator.py` already documents the intended behaviour — the
`divide` test fails until the fix is approved.

**Try it:** open `src/calculator.py`, ask the assistant to *"fix the divide by
zero bug"*, review the diff, then approve it. Nothing is written until you do.
""",
    "src/calculator.py": '''"""Sample calculator module for the Dev Studio walkthrough."""


def add(a, b):
    return a + b


def divide(a, b):
    # TODO: guard against division by zero
    return a / b


def is_zero(value):
    return value == None  # noqa: E711 - intentional, offline lint demo


def average(values=[]):
    if not values:
        return 0
    return sum(values) / len(values)


def describe(values):
    return f"{len(values)} value(s), average {average(values):.2f}"
''',
    "tests/test_calculator.py": '''"""Behaviour we expect from src.calculator.

The divide test fails until the AI-proposed fix is approved.
"""

from src.calculator import add, average, describe, divide


def test_add():
    assert add(2, 3) == 5


def test_average_empty():
    assert average([]) == 0


def test_average_values():
    assert average([2, 4]) == 3


def test_describe():
    assert describe([1, 3]) == "2 value(s), average 2.00"


def test_divide_by_zero_returns_none():
    assert divide(1, 0) is None
''',
    "notes/meeting-actions.md": """# Action items

- [ ] Fix `divide()` zero-division bug
- [ ] Replace `== None` with `is None`
- [ ] Remove the mutable default argument in `average()`
""",
}


def seed_sample(workspace_id: str, db=None) -> list[str]:
    """Create the sample project. Only writes files that do not exist yet."""
    return _store(db).seed_sample(workspace_id)


# --------------------------------------------------------------------------
# Offline analysis (no LLM required)
# --------------------------------------------------------------------------

# (pattern, languages, message, severity)
_LINT_RULES: tuple[tuple[re.Pattern[str], tuple[str, ...] | None, str, str], ...] = (
    (re.compile(r"^\s*except\s*:\s*(#.*)?$"), ("python",),
     "Bare `except:` also swallows KeyboardInterrupt — catch a specific exception.", "high"),
    (re.compile(r"(?<![=!<>])==\s*None\b"), ("python",),
     "Use `is None` instead of `== None`.", "low"),
    (re.compile(r"(?<![=!<>])!=\s*None\b"), ("python",),
     "Use `is not None` instead of `!= None`.", "low"),
    (re.compile(r"def\s+\w+\s*\([^)]*=\s*(\[\]|\{\})"), ("python",),
     "Mutable default argument — it is shared between every call.", "medium"),
    (re.compile(r"\b(eval|exec)\s*\("), ("python",),
     "`eval`/`exec` on untrusted input is a security risk.", "high"),
    (re.compile(r"\bos\.system\s*\("), ("python",),
     "Prefer `subprocess.run([...], check=True)` over `os.system`.", "medium"),
    (re.compile(r"/\s*\w+\s*$"), ("python",),
     "Possible division by zero — confirm the divisor cannot be 0.", "low"),
    (re.compile(r"console\.log\("), ("javascript", "typescript"),
     "Leftover `console.log` — remove it before shipping.", "low"),
    (re.compile(r"\bdebugger\b"), ("javascript", "typescript"),
     "Leftover `debugger` statement.", "medium"),
    (re.compile(r"[^=!<>]==[^=]"), ("javascript", "typescript"),
     "Use `===` instead of `==` to avoid type coercion.", "low"),
    (re.compile(r"\bvar\s+\w+"), ("javascript", "typescript"),
     "Prefer `const`/`let` over `var`.", "low"),
    (re.compile(r"\bprint\s*\("), ("python",),
     "Debug `print` left in the file — consider `logging`.", "info"),
)

_TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)", re.IGNORECASE)
_LONG_LINE_LIMIT = 120

_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)", re.MULTILINE)
_PY_CLASS_RE = re.compile(r"^\s*class\s+(\w+)", re.MULTILINE)
_JS_DEF_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)|"
    r"^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(",
    re.MULTILINE,
)
_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.,\s]+))", re.MULTILINE)
_JS_IMPORT_RE = re.compile(r"^\s*import\s+.*?from\s+['\"]([^'\"]+)['\"]", re.MULTILINE)


def find_todos(content: str, language: str = "") -> list[dict[str, Any]]:
    """All TODO/FIXME-style markers with line numbers."""
    out: list[dict[str, Any]] = []
    for lineno, line in enumerate((content or "").splitlines(), start=1):
        m = _TODO_RE.search(line)
        if m:
            out.append({
                "line": lineno,
                "kind": m.group(1).upper(),
                "text": m.group(2).strip(),
            })
    return out


def static_lint(content: str, language: str = "", path: str = "") -> list[dict[str, Any]]:
    """A deliberately small, deterministic linter (the offline 'review')."""
    findings: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for lineno, line in enumerate((content or "").splitlines(), start=1):
        stripped = line.strip()
        for pattern, langs, message, severity in _LINT_RULES:
            if langs is not None and language not in langs:
                continue
            if pattern.search(line):
                # Keep the noisiest rule (bare "possible div by zero") bounded.
                key = (lineno, message)
                if key in seen:
                    continue
                seen.add(key)
                findings.append({
                    "line": lineno,
                    "severity": severity,
                    "message": message,
                    "snippet": stripped[:160],
                })
        if len(line) > _LONG_LINE_LIMIT:
            findings.append({
                "line": lineno,
                "severity": "info",
                "message": f"Line is {len(line)} characters (limit {_LONG_LINE_LIMIT}).",
                "snippet": stripped[:160],
            })
        for todo in find_todos(line):
            findings.append({
                "line": lineno,
                "severity": "info",
                "message": f"Unresolved {todo['kind']}"
                           + (f": {todo['text']}" if todo["text"] else ""),
                "snippet": stripped[:160],
            })
    # Highest severity first, then by line.
    rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (rank.get(f["severity"], 9), f["line"]))
    return findings


def _symbols(content: str, language: str) -> tuple[list[str], list[str]]:
    if language == "python":
        classes = _PY_CLASS_RE.findall(content or "")
        funcs = _PY_DEF_RE.findall(content or "")
        return classes, funcs
    matches = _JS_DEF_RE.findall(content or "")
    funcs = [a or b for a, b in matches]
    return [], [f for f in funcs if f]


def _imports(content: str, language: str) -> list[str]:
    if language == "python":
        mods: list[str] = []
        for a, b in _PY_IMPORT_RE.findall(content or ""):
            if a:
                mods.append(a)
            elif b:
                mods.extend(m.strip() for m in b.split(",") if m.strip())
        return mods
    return _JS_IMPORT_RE.findall(content or "")


def file_overview(content: str, language: str, path: str) -> str:
    """Deterministic structural summary of one file."""
    lines = (content or "").splitlines()
    classes, funcs = _symbols(content or "", language)
    imports = _imports(content or "", language)
    todos = find_todos(content or "", language)

    parts = [f"`{path}` — {language or 'text'}, {len(lines)} lines."]
    if imports:
        shown = ", ".join(f"`{m}`" for m in imports[:8])
        more = f" (+{len(imports) - 8} more)" if len(imports) > 8 else ""
        parts.append(f"**Imports:** {shown}{more}")
    if classes:
        parts.append("**Classes:** " + ", ".join(f"`{c}`" for c in classes[:12]))
    if funcs:
        parts.append("**Functions:** " + ", ".join(f"`{f}`" for f in funcs[:16]))
    if not classes and not funcs:
        parts.append("No top-level classes or functions detected.")
    parts.append(f"**Markers:** {len(todos)} TODO/FIXME-style comment(s).")

    findings = static_lint(content or "", language, path)
    if findings:
        top = findings[:3]
        parts.append(
            "**Review highlights:** "
            + "; ".join(f"line {f['line']} — {f['message']}" for f in top)
        )
    return "\n\n".join(parts)


def flatten_paths(node: dict[str, Any], limit: int = 200) -> list[str]:
    out: list[str] = []

    def walk(n: dict[str, Any]) -> None:
        if len(out) >= limit:
            return
        if n.get("type") == "file" and n.get("path"):
            out.append(n["path"])
        for child in n.get("children", []) or []:
            walk(child)

    walk(node)
    return out


def tree_summary(node: dict[str, Any], limit: int = 60) -> str:
    paths = flatten_paths(node, limit=limit)
    if not paths:
        return "(the workspace is empty)"
    joined = "\n".join(f"- {p}" for p in paths)
    if len(paths) >= limit:
        joined += f"\n- … (truncated at {limit} files)"
    return joined


def _comment_prefix(language: str) -> str:
    return COMMENT_PREFIX.get(language, "#")


def fallback_code_answer(
    message: str,
    *,
    tree: dict[str, Any] | None = None,
    file_path: str | None = None,
    file_content: str | None = None,
    language: str = "plaintext",
    meeting_context: str | None = None,
    task_context: str | None = None,
) -> dict[str, Any]:
    """Answer using only deterministic analysis (no LLM).

    Implements the offline rung of the Dev Studio degradation ladder. Gives
    genuinely useful structural/static-analysis answers rather than pretending
    to reason.
    """
    q = (message or "").strip().lower()
    suggestions: list[dict[str, Any]] = []
    notice = (
        "⚠️ **Offline mode** — no LLM was reachable, so this is deterministic "
        "static analysis rather than a generated answer.\n\n"
    )

    wants_todo = any(k in q for k in ("todo", "fixme", "unfinished", "pending"))
    wants_review = any(
        k in q
        for k in (
            "bug", "review", "lint", "issue", "problem", "fix", "check",
            "dikkat", "kharab", "theek", "safe", "security",
        )
    )
    wants_explain = any(
        k in q
        for k in (
            "explain", "samjha", "samjhao", "describe", "what does", "kya karta",
            "walk me", "overview of this file", "structure of this file",
        )
    )
    wants_structure = any(
        k in q for k in ("structure", "tree", "files", "project", "repo", "kya hai", "layout")
    )
    wants_test = any(k in q for k in ("test", "spec", "pytest", "coverage", "unit"))

    body: str

    if file_content is not None and file_path and wants_todo:
        todos = find_todos(file_content, language)
        if todos:
            body = f"**{len(todos)} marker(s) in `{file_path}`**\n\n" + "\n".join(
                f"- line {t['line']}: **{t['kind']}** {t['text'] or '(no description)'}"
                for t in todos
            )
            first = todos[0]
            suggestions.append({
                "action": "propose_edit",
                "label": f"Resolve {first['kind']} on line {first['line']}",
                "file_path": file_path,
                "instruction": first["text"] or f"Resolve the {first['kind']} comment",
            })
        else:
            body = f"No TODO/FIXME markers in `{file_path}`. 🎉"

    elif file_content is not None and file_path and (wants_review or wants_explain):
        findings = static_lint(file_content, language, file_path)
        if wants_explain and not wants_review:
            body = file_overview(file_content, language, file_path)
        elif findings:
            body = (
                f"**{len(findings)} finding(s) in `{file_path}`**\n\n"
                + "\n".join(
                    f"- line {f['line']} · {f['severity']} — {f['message']}"
                    for f in findings[:12]
                )
            )
            if len(findings) > 12:
                body += f"\n- … and {len(findings) - 12} more"
            suggestions.append({
                "action": "propose_edit",
                "label": f"Address line {findings[0]['line']}",
                "file_path": file_path,
                "instruction": findings[0]["message"],
            })
        else:
            body = (
                file_overview(file_content, language, file_path)
                + "\n\nNo issues found by the offline linter."
            )

    elif wants_test and file_path:
        body = (
            f"I can scaffold a test module for `{file_path}`.\n\n"
            f"Add a file next to it (for Python, `tests/`) and assert the "
            f"documented behaviour. Approve the proposal below and I will write "
            f"the stub — you fill in the assertions."
        )
        suggestions.append({
            "action": "propose_edit",
            "label": "Scaffold a test module",
            "file_path": file_path,
            "instruction": "create a test scaffold for this module",
        })

    elif file_content is not None and file_path:
        body = file_overview(file_content, language, file_path)

    else:
        summary = tree_summary(tree or {}, limit=40)
        body = (
            f"Here is everything in this workspace ({len(flatten_paths(tree or {}, 500))} file(s)):\n\n"
            f"{summary}\n\n"
            "Open a file and ask me to explain it, list its TODO markers, or "
            "review it for bugs."
        )

    context_lines = []
    if file_path:
        context_lines.append(f"file `{file_path}`")
    if meeting_context:
        context_lines.append("the linked meeting")
    if task_context:
        context_lines.append("the linked task")
    if context_lines:
        body += "\n\n_Using " + ", ".join(context_lines) + " as context._"

    return {
        "answer": notice + body,
        "source": "fallback",
        "suggestions": suggestions,
    }


def fallback_code_proposal(
    file_path: str,
    content: str | None,
    instruction: str,
    language: str = "plaintext",
) -> dict[str, Any]:
    """Deterministic scaffold edit used when no LLM is reachable.

    Only ever *appends or prepends comments* / creates a test stub — it never
    rewrites logic it cannot understand. Honestly labelled as a scaffold.
    """
    original = content or ""
    prefix = _comment_prefix(language)
    text = instruction.strip() or "apply the requested change"
    lower = text.lower()

    if "test" in lower:
        stem = Path(file_path).stem
        proposed = (
            f"{prefix} Generated test scaffold for {file_path}\n"
            f"{prefix} TODO: replace the placeholder assertion with real expectations.\n\n"
            f'"""Tests for {stem}."""\n\n\n'
            f"def test_{stem}_placeholder():\n"
            f"    assert True  # TODO: import from {stem} and assert behaviour\n"
        )
        rationale = "Offline scaffold: created a placeholder test module for you to fill in."
    elif any(k in lower for k in ("doc", "comment", "header", "explain")):
        header = (
            f"{prefix} {file_path}\n"
            f"{prefix} Purpose: {text}\n"
            f"{prefix}\n"
            f"{prefix} NOTE: comment block added offline by SyncForge Dev Studio.\n"
        )
        proposed = f"{header}\n{original}" if original else header
        rationale = "Offline scaffold: prepended a documented header comment block."
    else:
        block = (
            f"\n\n{prefix} TODO(SyncForge AI, offline scaffold): {text}\n"
            f"{prefix} This is a placeholder — approve after a human/LLM fills in the change.\n"
        )
        proposed = original.rstrip("\n") + block
        rationale = (
            "Offline scaffold: appended a TODO marker describing the request. "
            "No LLM was available to author the actual code change."
        )

    return {
        "proposed_content": proposed,
        "rationale": rationale,
        "source": "fallback",
    }


# --------------------------------------------------------------------------
# LLM-backed assistance (with automatic fallback)
# --------------------------------------------------------------------------

CODE_CHAT_SYSTEM = """You are SyncForge Dev Studio, a senior engineer embedded in a
team workspace. You help with the code in front of you and with the meeting and
task context you are given.

Rules:
- Be concise and concrete. Short markdown, no filler.
- Only reference files and symbols that appear in the provided context. If you
  need something else, say which file to open.
- You cannot change files. You only advise; a human approves every edit.
- Support English and Hinglish; answer in the language of the question.
- If the workspace is empty, suggest creating the sample project.
"""

CODE_EDIT_SYSTEM = """You are SyncForge Dev Studio, a careful senior engineer.
You propose the complete new contents of exactly ONE file.

Respond with ONLY valid JSON, no prose and no markdown fences:
{"proposed_content": "the full new file contents", "rationale": "1-3 sentences"}

Rules:
- Return the ENTIRE file, never a patch, diff or excerpt.
- Preserve the existing style, formatting, indentation and language.
- Make the smallest change that satisfies the instruction.
- Do not add or remove imports unless the change requires it.
- Do not invent APIs, modules or helpers that are not already available.
- Keep the public behaviour identical unless the instruction says otherwise.
"""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated, {len(text) - limit} characters omitted]"


def _context_block(
    *,
    tree: dict[str, Any] | None,
    file_path: str | None,
    file_content: str | None,
    language: str,
    meeting_context: str | None,
    task_context: str | None,
) -> str:
    chunks: list[str] = []
    if meeting_context:
        chunks.append(f"## Linked meeting\n{meeting_context}")
    if task_context:
        chunks.append(f"## Linked task\n{task_context}")
    if tree is not None:
        chunks.append(f"## Workspace files\n{tree_summary(tree)}")
    if file_path and file_content is not None:
        chunks.append(
            f"## Open file: {file_path} (language: {language})\n"
            f"```{language}\n{_truncate(file_content, settings.DEVSTUDIO_CONTEXT_CHARS)}\n```"
        )
    return "\n\n".join(chunks) if chunks else "(no context provided)"


def ai_code_answer(
    message: str,
    *,
    history: Iterable[dict[str, str]] | None = None,
    tree: dict[str, Any] | None = None,
    file_path: str | None = None,
    file_content: str | None = None,
    language: str = "plaintext",
    meeting_context: str | None = None,
    task_context: str | None = None,
    allow_fallback: bool | None = None,
) -> dict[str, Any]:
    """Context-aware answer with the offline analyser as fallback.

    The returned dict always carries ``source`` (``"llm"`` or ``"fallback"``).
    """
    if allow_fallback is None:
        allow_fallback = settings.ALLOW_EXTRACTIVE_FALLBACK

    convo = ""
    turns = list(history or [])[-6:]
    if turns:
        lines = [
            f"{t.get('role', 'user').upper()}: {_truncate(str(t.get('content', '')), 1500)}"
            for t in turns
            if t.get("content")
        ]
        if lines:
            convo = "## Conversation so far\n" + "\n".join(lines) + "\n\n"

    user = (
        f"{_context_block(tree=tree, file_path=file_path, file_content=file_content, language=language, meeting_context=meeting_context, task_context=task_context)}\n\n"
        f"{convo}"
        f"## Question\n{message}"
    )

    try:
        from app.services.llm import chat_completion

        answer = chat_completion(
            system=CODE_CHAT_SYSTEM,
            user=user,
            model=settings.CODE_MODEL,
            temperature=0.2,
            max_tokens=2048,
        )
        if not answer or not answer.strip():
            raise ValueError("empty answer")
        return {
            "answer": answer.strip(),
            "source": "llm",
            "suggestions": _suggest_from_state(file_path, file_content, language),
        }
    except Exception as exc:
        if not allow_fallback:
            raise
        logger.warning(
            "Dev Studio chat LLM unavailable (%s); using offline analyser", exc
        )
        result = fallback_code_answer(
            message,
            tree=tree,
            file_path=file_path,
            file_content=file_content,
            language=language,
            meeting_context=meeting_context,
            task_context=task_context,
        )
        result["fallback_reason"] = str(exc)[:300]
        return result


def _suggest_from_state(
    file_path: str | None, file_content: str | None, language: str
) -> list[dict[str, Any]]:
    """Small, deterministic follow-up suggestions shown next to an answer."""
    if not file_path or file_content is None:
        return []
    findings = static_lint(file_content, language, file_path)
    if not findings:
        return []
    return [{
        "action": "propose_edit",
        "label": f"Ask AI to fix line {findings[0]['line']}",
        "file_path": file_path,
        "instruction": findings[0]["message"],
    }]


def ai_code_proposal(
    file_path: str,
    instruction: str,
    *,
    content: str | None,
    language: str = "plaintext",
    meeting_context: str | None = None,
    task_context: str | None = None,
    allow_fallback: bool | None = None,
) -> dict[str, Any]:
    """Produce the *suggested* new contents of one file (never applied here)."""
    if allow_fallback is None:
        allow_fallback = settings.ALLOW_EXTRACTIVE_FALLBACK

    existing = content or ""
    user = (
        f"{_context_block(tree=None, file_path=file_path, file_content=existing, language=language, meeting_context=meeting_context, task_context=task_context)}\n\n"
        f"## Instruction\n{instruction}\n\n"
        f"{'Create this file (it does not exist yet).' if not existing else 'Rewrite the file accordingly.'}"
    )

    try:
        from app.services.llm import structured_completion

        raw = structured_completion(
            system=CODE_EDIT_SYSTEM,
            user=user,
            model=settings.CODE_MODEL,
            temperature=0.1,
            max_tokens=4096,
        )
        if not isinstance(raw, dict):
            raise ValueError("proposal was not a JSON object")
        proposed = raw.get("proposed_content")
        if not isinstance(proposed, str) or not proposed.strip():
            raise ValueError("proposal had no proposed_content")
        if proposed == existing:
            raise ValueError("proposal did not change anything")
        rationale = raw.get("rationale")
        return {
            "proposed_content": proposed,
            "rationale": str(rationale).strip() if rationale else None,
            "source": "llm",
        }
    except Exception as exc:
        if not allow_fallback:
            raise
        logger.warning(
            "Dev Studio proposal LLM unavailable (%s); using offline scaffold", exc
        )
        result = fallback_code_proposal(file_path, existing, instruction, language)
        result["fallback_reason"] = str(exc)[:300]
        return result
