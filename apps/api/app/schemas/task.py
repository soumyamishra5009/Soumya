"""Task schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    workspace_id: str
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    status: str = Field(default="todo", pattern=r"^(todo|in_progress|review|done|blocked|cancelled)$")
    priority: str = Field(default="medium", pattern=r"^(low|medium|high|urgent)$")
    assignee_id: str | None = None
    meeting_id: str | None = None
    decision_id: str | None = None
    due_date: datetime | None = None
    start_date: datetime | None = None
    estimated_hours: float | None = Field(default=None, gt=0, le=10000)
    tags: list[str] | None = None
    sequence: int = 0


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: str | None = Field(default=None, pattern=r"^(todo|in_progress|review|done|blocked|cancelled)$")
    priority: str | None = Field(default=None, pattern=r"^(low|medium|high|urgent)$")
    assignee_id: str | None = None
    due_date: datetime | None = None
    start_date: datetime | None = None
    estimated_hours: float | None = Field(default=None, gt=0, le=10000)
    actual_hours: float | None = Field(default=None, ge=0, le=10000)
    tags: list[str] | None = None
    sequence: int | None = None


class TaskOut(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None = None
    meeting_id: str | None = None
    decision_id: str | None = None
    title: str
    description: str | None = None
    status: str
    priority: str
    assignee_id: str | None = None
    reporter_id: str | None = None
    due_date: datetime | None = None
    start_date: datetime | None = None
    completed_at: datetime | None = None
    estimated_hours: float | None = None
    actual_hours: float | None = None
    tags: list[str] | None = None
    sequence: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
