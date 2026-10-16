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


class MemberOut(BaseModel):
    """A workspace member enriched with the user's profile (for assignees)."""

    membership_id: str
    user_id: str
    name: str
    email: str
    image: str | None = None
    role: str
    is_owner: bool = False
    accepted_at: datetime | None = None
    invited_at: datetime


class MemberAdd(BaseModel):
    email: str = Field(
        min_length=5,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    role: str = Field(default="member", pattern=r"^(admin|member|viewer)$")
