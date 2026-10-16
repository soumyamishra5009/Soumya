"""Dev Studio schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class FileNode(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir"]
    size: int | None = None
    language: str | None = None
    editable: bool | None = None
    children: list["FileNode"] | None = None


class StudioTree(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir"] = "dir"
    children: list[FileNode] = Field(default_factory=list)
    empty: bool = False
    count: int = 0
    truncated: bool = False


class StudioFile(BaseModel):
    path: str
    name: str
    language: str
    content: str
    size: int
    editable: bool = True
    hash: str
    updated_at: str | None = None


class FileWriteRequest(BaseModel):
    content: str = Field(default="", max_length=2_000_000)


class FileCreateRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    kind: Literal["file", "dir"] = "file"
    content: str = Field(default="", max_length=2_000_000)


class EntryOut(BaseModel):
    path: str
    name: str | None = None
    type: Literal["file", "dir"] | None = None
    deleted: bool | None = None


class SeedResult(BaseModel):
    created: list[str]
    skipped: int = 0


class LintFinding(BaseModel):
    line: int
    severity: str
    message: str
    snippet: str = ""


class LintResult(BaseModel):
    path: str
    language: str
    findings: list[LintFinding] = Field(default_factory=list)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20_000)


class StudioChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    file_path: str | None = None
    meeting_id: str | None = None
    task_id: str | None = None
    history: list[ChatTurn] = Field(default_factory=list)


class ChatSuggestion(BaseModel):
    action: str = "propose_edit"
    label: str
    file_path: str | None = None
    instruction: str | None = None


class StudioChatResponse(BaseModel):
    answer: str
    source: str
    suggestions: list[ChatSuggestion] = Field(default_factory=list)
    context_used: dict[str, Any] = Field(default_factory=dict)
    fallback_reason: str | None = None


class ProposalCreateRequest(BaseModel):
    file_path: str = Field(min_length=1, max_length=1000)
    instruction: str = Field(min_length=1, max_length=4000)
    meeting_id: str | None = None
    task_id: str | None = None


class CodeProposalOut(BaseModel):
    id: str
    workspace_id: str
    file_path: str
    language: str | None = None
    original_content: str | None = None
    proposed_content: str
    rationale: str | None = None
    source: str
    status: str
    base_hash: str | None = None
    added_lines: int = 0
    removed_lines: int = 0
    meeting_id: str | None = None
    task_id: str | None = None
    created_by: str | None = None
    decided_by: str | None = None
    created_at: datetime
    decided_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProposalDecisionOut(BaseModel):
    proposal: CodeProposalOut
    applied: bool = False
    message: str = ""
