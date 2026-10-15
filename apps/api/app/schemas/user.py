"""User schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    image: str | None = None
    role: str
    is_active: bool
    email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}
