"""Workspace schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    slug: str | None = Field(default=None, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class WorkspaceOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    slug: str
    owner_id: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceMemberOut(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    role: str
    invited_at: datetime

    model_config = {"from_attributes": True}
