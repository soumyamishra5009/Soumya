"""SQLAlchemy models package. Importing this package registers all models
with Base.metadata (used by Alembic autogenerate)."""

from app.models.base import Base, generate_uuid  # noqa: F401
from app.models.enums import (  # noqa: F401
    UserRole,
    WorkspaceRole,
    MeetingStatus,
    TaskStatus,
    TaskPriority,
    DecisionImpact,
    ProposalStatus,
)
from app.models.user import User, Account  # noqa: F401
from app.models.workspace import Workspace, WorkspaceMember  # noqa: F401
from app.models.meeting import Meeting, Transcript, TranscriptSegment, Decision  # noqa: F401
from app.models.task import Task  # noqa: F401
from app.models.code import CodeProposal  # noqa: F401

__all__ = [
    "Base",
    "generate_uuid",
    "UserRole",
    "WorkspaceRole",
    "MeetingStatus",
    "TaskStatus",
    "TaskPriority",
    "DecisionImpact",
    "ProposalStatus",
    "User",
    "Account",
    "Workspace",
    "WorkspaceMember",
    "Meeting",
    "Transcript",
    "TranscriptSegment",
    "Decision",
    "Task",
    "CodeProposal",
]
