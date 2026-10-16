"""Ship service: turn a reviewed change set into a branch / commit / pull request.

Two providers behind one interface:

* **local** — a real branch + commit inside the Dev Studio sandbox, merged back
  into the base branch on approval. Offline, zero config.
* **github** — the identical snapshot pushed to a remote repo and opened as a
  pull request through the REST API (needs ``GITHUB_TOKEN``).

Both are human-gated: :func:`open_change` is only called after a person presses
"Open pull request". The local provider additionally refuses to open if the
sandbox drifted after the proposal was created, so what gets committed is exactly
what was reviewed.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.models.enums import RepoProvider
from app.services import githost, localgit

logger = logging.getLogger(__name__)


class ShipError(RuntimeError):
    """Raised when a change set cannot be shipped."""


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, limit: int = 40) -> str:
    slug = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return slug[:limit].strip("-") or "change"


def make_branch_name(title: str, seed: str) -> str:
    """A safe, readable, unique-enough branch name like ``syncforge/fix-divide-a1b2c3d4``."""
    tail = re.sub(r"[^a-z0-9]", "", (seed or "").lower())[:8] or "0000"
    return localgit.validate_branch(f"syncforge/{slugify(title)}-{tail}")


def is_github(provider: str) -> bool:
    return provider == RepoProvider.GITHUB.value


def snapshot_matches(workspace_id: str, files: list[dict[str, Any]]) -> bool:
    """True when the sandbox still contains exactly the reviewed change set."""
    current = localgit.snapshot(workspace_id)["files"]
    reviewed = {
        f["path"]: (f.get("deleted"), f.get("content"))
        for f in files
        if isinstance(f, dict)
    }
    live = {
        f["path"]: (f.get("deleted"), f.get("content"))
        for f in current
        if isinstance(f, dict)
    }
    return reviewed == live


def open_change(
    provider: str,
    *,
    workspace_id: str,
    repo_full_name: str | None,
    base_branch: str,
    branch: str,
    files: list[dict[str, Any]],
    title: str,
    body: str | None,
    author_name: str | None = None,
    author_email: str | None = None,
) -> dict[str, Any]:
    """Create the branch/commit (and PR when remote). Returns tracking metadata."""
    if is_github(provider):
        if not repo_full_name:
            raise ShipError("No GitHub repository is connected")
        if not githost.configured():
            raise ShipError(
                "No GitHub token configured. Set GITHUB_TOKEN, or use the offline "
                "local git provider."
            )
        commit_sha = githost.push_branch(
            repo_full_name,
            base_branch=base_branch,
            branch=branch,
            files=files,
            message=title,
        )
        pr = githost.create_pull_request(
            repo_full_name, title=title, head=branch, base=base_branch, body=body or ""
        )
        return {
            "provider": provider,
            "commit_sha": commit_sha,
            "external_number": pr.get("number"),
            "external_url": pr.get("url"),
        }

    # Local provider: the sandbox must match exactly what was reviewed.
    localgit.ensure_repo(workspace_id, author_name=author_name, author_email=author_email)
    if not snapshot_matches(workspace_id, files):
        raise ShipError(
            "The sandbox changed after this proposal was created. "
            "Close it and create a fresh pull-request proposal."
        )
    localgit.create_branch(workspace_id, branch)
    message = title if not body else f"{title}\n\n{body}"
    commit_sha = localgit.commit_all(
        workspace_id, message, author_name=author_name, author_email=author_email
    )
    return {
        "provider": provider,
        "commit_sha": commit_sha,
        "external_number": None,
        "external_url": None,
    }


def merge_change(
    provider: str,
    *,
    workspace_id: str,
    repo_full_name: str | None,
    base_branch: str,
    branch: str,
    external_number: int | None = None,
) -> dict[str, Any]:
    if is_github(provider):
        if not repo_full_name or external_number is None:
            raise ShipError("This proposal has no GitHub pull request to merge")
        return githost.merge_pull_request(repo_full_name, external_number)

    result = localgit.merge(workspace_id, branch, base=base_branch)
    return {"merged": True, "sha": result.get("sha"), "branch": result.get("branch")}


def close_change(
    provider: str,
    *,
    workspace_id: str,
    repo_full_name: str | None,
    base_branch: str,
    branch: str,
    external_number: int | None = None,
) -> dict[str, Any]:
    if is_github(provider):
        if not repo_full_name or external_number is None:
            raise ShipError("This proposal has no GitHub pull request to close")
        return githost.close_pull_request(repo_full_name, external_number)

    localgit.checkout(workspace_id, base_branch)
    localgit.delete_branch(workspace_id, branch, base=base_branch)
    return {"closed": True, "branch": branch}
