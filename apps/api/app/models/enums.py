"""Shared enum definitions for the SyncForge models."""
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class WorkspaceRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class MeetingStatus(str, enum.Enum):
    UPLOADING = "uploading"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class DecisionImpact(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProposalStatus(str, enum.Enum):
    """Lifecycle of an AI code-change proposal (human-in-the-loop).

    Nothing is ever applied automatically: a proposal stays ``pending`` until a
    human explicitly approves (written to disk) or rejects it.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RepoProvider(str, enum.Enum):
    """Where a workspace's code is shipped.

    ``local`` is a real git repository inside the Dev Studio sandbox — it works
    offline with no account and no token, which is the default. ``github`` pushes
    the same change set to a remote repository through the REST API (requires
    ``GITHUB_TOKEN``).
    """

    LOCAL = "local"
    GITHUB = "github"


class PullRequestStatus(str, enum.Enum):
    """Lifecycle of a pull-request proposal (human-in-the-loop).

    A proposal is built as a ``draft`` (a snapshot of the current diff) and is
    only turned into a real branch/commit/PR when a human opens it.
    """

    DRAFT = "draft"
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"
    FAILED = "failed"


class PlanStatus(str, enum.Enum):
    """Lifecycle of a Meeting→Code plan."""

    DRAFT = "draft"
    APPLIED = "applied"
