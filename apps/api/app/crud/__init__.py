"""CRUD operations (thin data-access layer)."""

from app.crud.user import user as user_crud  # noqa: F401
from app.crud.workspace import workspace as workspace_crud  # noqa: F401
from app.crud.meeting import (  # noqa: F401
    meeting as meeting_crud,
    transcript as transcript_crud,
    decision as decision_crud,
)
from app.crud.task import task as task_crud  # noqa: F401

__all__ = [
    "user_crud",
    "workspace_crud",
    "meeting_crud",
    "transcript_crud",
    "decision_crud",
    "task_crud",
]
