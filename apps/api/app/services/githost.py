"""GitHub provider: open the *same* approved change set as a real pull request.

This is the remote half of the Phase 4 "ship it" story. It is entirely optional:
without a ``GITHUB_TOKEN`` every call raises :class:`GitHubError` with a clear
message, and the local git provider keeps working. No token is ever stored in
the database — it is read from the environment here, at call time.

The change set is pushed with the Git database API (blobs → tree → commit → ref)
so we never need a local clone of the remote repository.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0
_FULL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


class GitHubError(RuntimeError):
    """Raised when GitHub is not configured or the API call fails."""


def configured() -> bool:
    return bool((settings.GITHUB_TOKEN or "").strip())


def validate_full_name(full_name: str) -> str:
    name = (full_name or "").strip().strip("/")
    if not _FULL_NAME_RE.match(name):
        raise GitHubError("Repository must be given as 'owner/repo'")
    return name


def _headers() -> dict[str, str]:
    token = (settings.GITHUB_TOKEN or "").strip()
    if not token:
        raise GitHubError(
            "No GitHub token configured. Set GITHUB_TOKEN to push a pull request, "
            "or use the offline 'local git' provider."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Cognix",
    }


def _base() -> str:
    return (settings.GITHUB_API_URL or "https://api.github.com").rstrip("/")


def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{_base()}{path}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.request(method, url, headers=_headers(), **kwargs)
    except httpx.HTTPError as exc:
        raise GitHubError(f"Could not reach GitHub: {exc}") from exc

    if resp.status_code >= 400:
        detail = ""
        try:
            detail = (resp.json() or {}).get("message", "")
        except Exception:  # pragma: no cover - non-JSON error body
            detail = resp.text[:200]
        raise GitHubError(f"GitHub API {resp.status_code}: {detail or resp.text[:200]}")
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


# --------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------


def get_repo(full_name: str) -> dict[str, Any]:
    full_name = validate_full_name(full_name)
    data = _request("GET", f"/repos/{full_name}")
    return {
        "full_name": data.get("full_name", full_name),
        "default_branch": data.get("default_branch", "main"),
        "private": bool(data.get("private")),
        "html_url": data.get("html_url"),
        "permissions": data.get("permissions") or {},
    }


def get_ref_sha(full_name: str, branch: str) -> str:
    data = _request("GET", f"/repos/{full_name}/git/ref/heads/{branch}")
    return data["object"]["sha"]


def get_commit_tree_sha(full_name: str, commit_sha: str) -> str:
    data = _request("GET", f"/repos/{full_name}/git/commits/{commit_sha}")
    return data["tree"]["sha"]


def open_pull_requests(full_name: str, *, state: str = "open") -> list[dict[str, Any]]:
    full_name = validate_full_name(full_name)
    data = _request("GET", f"/repos/{full_name}/pulls", params={"state": state, "per_page": 50})
    return [
        {"number": p["number"], "title": p["title"], "url": p["html_url"], "state": p["state"]}
        for p in (data or [])
    ]


# --------------------------------------------------------------------------
# Write
# --------------------------------------------------------------------------


def push_branch(
    full_name: str,
    *,
    base_branch: str,
    branch: str,
    files: list[dict[str, Any]],
    message: str,
) -> str:
    """Create ``branch`` from ``base_branch`` with ``files`` applied. Returns the commit sha."""
    full_name = validate_full_name(full_name)
    base_sha = get_ref_sha(full_name, base_branch)
    base_tree = get_commit_tree_sha(full_name, base_sha)

    tree_entries: list[dict[str, Any]] = []
    for f in files:
        path = f.get("path")
        if not path:
            continue
        if f.get("deleted"):
            # A null sha removes the path from the tree.
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            continue
        blob = _request(
            "POST",
            f"/repos/{full_name}/git/blobs",
            json={"content": f.get("content") or "", "encoding": "utf-8"},
        )
        tree_entries.append({
            "path": path, "mode": "100644", "type": "blob", "sha": blob["sha"],
        })

    if not tree_entries:
        raise GitHubError("Nothing to push — the change set is empty")

    tree = _request(
        "POST",
        f"/repos/{full_name}/git/trees",
        json={"base_tree": base_tree, "tree": tree_entries},
    )
    commit = _request(
        "POST",
        f"/repos/{full_name}/git/commits",
        json={
            "message": message,
            "tree": tree["sha"],
            "parents": [base_sha],
        },
    )
    _request(
        "POST",
        f"/repos/{full_name}/git/refs",
        json={"ref": f"refs/heads/{branch}", "sha": commit["sha"]},
    )
    return commit["sha"]


def create_pull_request(
    full_name: str, *, title: str, head: str, base: str, body: str
) -> dict[str, Any]:
    full_name = validate_full_name(full_name)
    data = _request(
        "POST",
        f"/repos/{full_name}/pulls",
        json={"title": title, "head": head, "base": base, "body": body or ""},
    )
    return {
        "number": data.get("number"),
        "url": data.get("html_url"),
        "state": data.get("state"),
    }


def merge_pull_request(full_name: str, number: int, *, base: str | None = None) -> dict[str, Any]:
    full_name = validate_full_name(full_name)
    data = _request(
        "PUT",
        f"/repos/{full_name}/pulls/{number}/merge",
        json={"merge_method": "merge"},
    )
    return {"merged": data.get("merged", False), "message": data.get("message", "")}


def close_pull_request(full_name: str, number: int) -> dict[str, Any]:
    full_name = validate_full_name(full_name)
    data = _request(
        "PATCH", f"/repos/{full_name}/pulls/{number}", json={"state": "closed"}
    )
    return {"number": data.get("number"), "state": data.get("state")}
