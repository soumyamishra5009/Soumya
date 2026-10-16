"""Phase 5 schemas: sandboxed test runs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TestRunRequest(BaseModel):
    kind: Literal["auto", "python", "node"] = "auto"
    target: str | None = Field(default=None, max_length=1000)
    timeout: int | None = Field(default=None, ge=5, le=300)
    prefer_pytest: bool | None = None


class TestRunOut(BaseModel):
    id: str
    workspace_id: str
    kind: str
    runner: str
    command: str = ""
    target: str | None = None
    status: str
    exit_code: int | None = None
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration_ms: int = 0
    output: str = ""
    output_truncated: bool = False
    source: str = "local"
    created_by: str | None = None
    created_at: datetime
    summary: str = ""

    model_config = {"from_attributes": True}
