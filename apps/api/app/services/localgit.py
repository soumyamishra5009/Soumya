"""Local git provider: a real git repository inside the Dev Studio sandbox.

This is the offline-first half of the Phase 4 "ship it" story. It needs no
account, no token and no network: :func:`ensure_repo` turns a workspace sandbox
into a git repository with a baseline commit, and the studio's human-approved
edits then show up as ordinary working-tree changes that can be reviewed,
committed to a branch, and merged — the same shapes as a pull request.

Everything is scoped to ``settings.DEVSTUDIO_ROOT/<workspace_id>`` and every
argument is passed as a list (never through a shell), so nothing here can reach
files outside the sandbox or be used for command injection.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from app.services import devstudio

logger = logging.getLogger(__name__)

DEFAULT_BRANCH = "main"
# Generous: the first git command on a freshly created repo can be slow while the
# OS indexes/scan the new .git directory.
GIT_TIMEOUT = 60.0

_AI_NAME = "SyncForge AI"
_AI_EMAIL = "ai@syncforge.local"

# Per-repo ignores live in .git/info/exclude so the working tree (and the studio
# file tree) stays exactly what the user sees.
_EXCLUDE = """# SyncForge Dev Studio sandbox — local ignores (not committed)
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
node_modules/
*.log
.env
.DS_Store
"""

_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")

_STATUS_LABELS = {
    "M": "modified",
    "A": "added",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "??": "untracked",
    "U": "conflicted",
}


class GitError(RuntimeError):
    """Raised when git is unavailable or an operation fails."""


# --------------------------------------------------------------------------
# Process plumbing
# --------------------------------------------------------------------------


def available() -> bool:
    """True when a usable ``git`` executable is on PATH."""
    try:
        proc = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, timeout=10
        )
        return proc.returncode == 0
    except Exception:  # pragma: no cover - depends on the host
        return False


def _root(workspace_id: str) -> Path:
    root = devstudio.workspace_root(workspace_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run(
    workspace_id: str,
    args: list[str],
    *,
    check: bool = True,
    timeout: float = GIT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    root = _root(workspace_id)
    env = dict(os.environ)
    # Never block on a credential prompt; never read system-level config that
    # could enable hooks or commit signing in an unrelated environment; never
    # launch a pager.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_PAGER"] = "cat"
    env["PAGER"] = "cat"
    cmd = [
        "git",
        "--no-pager",
        "-c",
        "core.quotepath=false",
        "-c",
        "core.autocrlf=false",
        *args,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            # Never inherit a console/tty: a server process may have no usable
            # stdin, and a stray prompt or pager would then block forever.
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:  # pragma: no cover - host dependent
        raise GitError("git is not installed on this machine") from exc
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - host dependent
        raise GitError("git command timed out") from exc

    if check and proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "git command failed").strip()
        raise GitError(message[:800])
    return proc


def _identity_args(name: str | None, email: str | None) -> list[str]:
    return [
        "-c", f"user.name={name or _AI_NAME}",
        "-c", f"user.email={email or _AI_EMAIL}",
        "-c", "commit.gpgsign=false",
    ]


def _write_exclude(root: Path) -> None:
    try:
        info = root / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text(_EXCLUDE, encoding="utf-8")
    except OSError:  # pragma: no cover - best effort
        logger.debug("could not write .git/info/exclude", exc_info=True)


# --------------------------------------------------------------------------
# Repository state
# --------------------------------------------------------------------------


def is_repo(workspace_id: str) -> bool:
    return (devstudio.workspace_root(workspace_id) / ".git").exists()


def _has_head(workspace_id: str) -> bool:
    if not is_repo(workspace_id):
        return False
    proc = _run(workspace_id, ["rev-parse", "--verify", "-q", "HEAD"], check=False)
    return proc.returncode == 0


def current_branch(workspace_id: str) -> str:
    if not is_repo(workspace_id):
        return DEFAULT_BRANCH
    proc = _run(workspace_id, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    branch = (proc.stdout or "").strip()
    return branch if branch and branch != "HEAD" else DEFAULT_BRANCH


def branch_exists(workspace_id: str, branch: str) -> bool:
    proc = _run(
        workspace_id, ["rev-parse", "--verify", "-q", f"refs/heads/{branch}"], check=False
    )
    return proc.returncode == 0


def validate_branch(name: str) -> str:
    """Reject anything git would refuse, and anything that looks like an option."""
    name = (name or "").strip()
    if not name or not _BRANCH_RE.match(name):
        raise GitError(f"Invalid branch name: {name!r}")
    if name.startswith("-") or name.endswith(("/", ".")) or name.endswith(".lock"):
        raise GitError(f"Invalid branch name: {name!r}")
    if any(bad in name for bad in ("..", "@{", "//", "\\", " ")):
        raise GitError(f"Invalid branch name: {name!r}")
    return name


def ensure_repo(
    workspace_id: str,
    *,
    author_name: str | None = None,
    author_email: str | None = None,
) -> dict[str, Any]:
    """Create the repo (if needed) and a baseline commit (if the tree is not empty)."""
    root = _root(workspace_id)
    initialised = False
    if not is_repo(workspace_id):
        _run(workspace_id, ["init", "-b", DEFAULT_BRANCH])
        initialised = True

    _write_exclude(root)
    _run(workspace_id, ["config", "user.name", author_name or _AI_NAME])
    _run(workspace_id, ["config", "user.email", author_email or _AI_EMAIL])

    baseline: str | None = None
    if not _has_head(workspace_id):
        _run(workspace_id, ["add", "-A"])
        staged = _run(workspace_id, ["diff", "--cached", "--name-only"], check=False)
        if (staged.stdout or "").strip():
            args = [*_identity_args(author_name, author_email), "commit", "-m", "chore: baseline sandbox snapshot"]
            _run(workspace_id, args)
        else:
            args = [*_identity_args(author_name, author_email), "commit", "-m", "chore: initialise sandbox", "--allow-empty"]
            _run(workspace_id, args)
        baseline = _run(workspace_id, ["rev-parse", "HEAD"], check=False).stdout.strip() or None

    return {
        "initialized": initialised,
        "baseline_commit": baseline,
        "branch": current_branch(workspace_id),
        "available": True,
    }


# --------------------------------------------------------------------------
# Working tree
# --------------------------------------------------------------------------


def _status_label(code: str) -> str:
    if code in _STATUS_LABELS:
        return _STATUS_LABELS[code]
    return _STATUS_LABELS.get(code[:1], "modified")


def changed_files(workspace_id: str) -> list[dict[str, str]]:
    """Working-tree changes as ``[{path, status}]`` (untracked files included)."""
    if not _has_head(workspace_id):
        return []
    proc = _run(
        workspace_id, ["status", "--porcelain", "--untracked-files=all"], check=False
    )
    out: list[dict[str, str]] = []
    for raw in (proc.stdout or "").splitlines():
        if len(raw) < 4:
            continue
        code = raw[:2].strip() or "??"
        path = raw[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if not path:
            continue
        out.append({"path": path, "status": _status_label(code)})
    return out


def diff(workspace_id: str) -> str:
    """Unified diff of the working tree against HEAD (untracked files included)."""
    if not _has_head(workspace_id):
        return ""
    # Mark untracked files as intent-to-add so `git diff` shows their contents.
    _run(workspace_id, ["add", "-A", "-N"], check=False)
    proc = _run(workspace_id, ["diff", "--no-color", "--no-ext-diff"], check=False)
    return proc.stdout or ""


def log(workspace_id: str, limit: int = 20) -> list[dict[str, str]]:
    if not _has_head(workspace_id):
        return []
    fmt = "%H%x1f%an%x1f%ae%x1f%aI%x1f%s"
    proc = _run(
        workspace_id, ["log", f"-{max(1, min(limit, 200))}", f"--pretty=format:{fmt}"],
        check=False,
    )
    commits: list[dict[str, str]] = []
    for line in (proc.stdout or "").splitlines():
        parts = line.split("\x1f")
        if len(parts) < 5:
            continue
        commits.append({
            "sha": parts[0],
            "author_name": parts[1],
            "author_email": parts[2],
            "date": parts[3],
            "message": parts[4],
        })
    return commits


def branches(workspace_id: str) -> list[str]:
    if not is_repo(workspace_id):
        return []
    proc = _run(
        workspace_id, ["branch", "--format=%(refname:short)"], check=False
    )
    return [b.strip() for b in (proc.stdout or "").splitlines() if b.strip()]


def _head_content(workspace_id: str, rel_path: str) -> str:
    proc = _run(workspace_id, ["show", f"HEAD:{rel_path}"], check=False)
    return proc.stdout if proc.returncode == 0 else ""


def status(workspace_id: str) -> dict[str, Any]:
    """A compact, UI-friendly picture of the sandbox repository."""
    root = devstudio.workspace_root(workspace_id)
    if not is_repo(workspace_id):
        return {
            "available": available(),
            "initialized": False,
            "branch": None,
            "branches": [],
            "clean": True,
            "changed_files": [],
            "commit_count": 0,
        }
    files = changed_files(workspace_id)
    commits = log(workspace_id, limit=200)
    return {
        "available": True,
        "initialized": True,
        "branch": current_branch(workspace_id),
        "branches": branches(workspace_id),
        "clean": len(files) == 0,
        "changed_files": files,
        "commit_count": len(commits),
    }


def snapshot(workspace_id: str) -> dict[str, Any]:
    """Capture the current change set so it can be shipped exactly as reviewed.

    Binary/uneditable files are skipped and reported in ``skipped``.
    """
    entries = changed_files(workspace_id)
    files: list[dict[str, Any]] = []
    skipped: list[str] = []
    added_total = removed_total = 0

    for entry in entries:
        rel = entry["path"]
        if not devstudio.is_editable(rel):
            skipped.append(rel)
            continue
        try:
            path, rel = devstudio.resolve_path(workspace_id, rel)
        except devstudio.SandboxError:
            skipped.append(entry["path"])
            continue

        deleted = not path.exists()
        content: str | None = None
        if not deleted and path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                skipped.append(rel)
                continue
        original = "" if deleted else _head_content(workspace_id, rel)
        added, removed = devstudio.diff_stats(original, content or "")
        added_total += added
        removed_total += removed
        files.append({
            "path": rel,
            "content": content,
            "deleted": deleted,
            "status": entry["status"],
            "added_lines": added,
            "removed_lines": removed,
        })

    return {
        "branch": current_branch(workspace_id),
        "files": files,
        "skipped": skipped,
        "file_count": len(files),
        "added_lines": added_total,
        "removed_lines": removed_total,
        "diff": diff(workspace_id),
    }


# --------------------------------------------------------------------------
# Commit / branch / merge
# --------------------------------------------------------------------------


def create_branch(workspace_id: str, branch: str) -> str:
    branch = validate_branch(branch)
    if branch_exists(workspace_id, branch):
        _run(workspace_id, ["checkout", branch])
    else:
        _run(workspace_id, ["checkout", "-b", branch])
    return branch


def commit_all(
    workspace_id: str,
    message: str,
    *,
    author_name: str | None = None,
    author_email: str | None = None,
) -> str:
    """Stage everything and commit. Raises :class:`GitError` if nothing changed."""
    if not _has_head(workspace_id):
        raise GitError("The sandbox repository has no baseline commit")
    _run(workspace_id, ["add", "-A"])
    staged = _run(workspace_id, ["diff", "--cached", "--name-only"], check=False)
    if not (staged.stdout or "").strip():
        raise GitError("Nothing to commit — the sandbox has no changes")
    subject = (message or "SyncForge change").strip().splitlines()[0][:200]
    _run(
        workspace_id,
        [*_identity_args(author_name, author_email), "commit", "-m", subject],
    )
    return _run(workspace_id, ["rev-parse", "HEAD"], check=False).stdout.strip()


def checkout(workspace_id: str, branch: str) -> str:
    branch = validate_branch(branch)
    _run(workspace_id, ["checkout", branch])
    return branch


def merge(workspace_id: str, branch: str, *, base: str | None = None) -> dict[str, Any]:
    base_branch = validate_branch(base or DEFAULT_BRANCH)
    branch = validate_branch(branch)
    if not branch_exists(workspace_id, branch):
        raise GitError(f"Branch {branch!r} does not exist")
    _run(workspace_id, ["checkout", base_branch])
    proc = _run(
        workspace_id,
        ["merge", "--no-ff", "-m", f"Merge {branch} into {base_branch}", branch],
        check=False,
    )
    if proc.returncode != 0:
        _run(workspace_id, ["merge", "--abort"], check=False)
        raise GitError((proc.stdout or proc.stderr or "merge failed").strip()[:800])
    return {
        "branch": base_branch,
        "sha": _run(workspace_id, ["rev-parse", "HEAD"], check=False).stdout.strip(),
    }


def delete_branch(workspace_id: str, branch: str, *, base: str | None = None) -> None:
    branch = validate_branch(branch)
    if current_branch(workspace_id) == branch:
        _run(workspace_id, ["checkout", validate_branch(base or DEFAULT_BRANCH)], check=False)
    _run(workspace_id, ["branch", "-D", branch], check=False)
