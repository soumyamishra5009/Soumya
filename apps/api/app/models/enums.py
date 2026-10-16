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
