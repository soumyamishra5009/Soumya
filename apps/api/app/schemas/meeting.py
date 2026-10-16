"""Meeting, transcript, decision and summary schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class MeetingCreate(BaseModel):
    workspace_id: str
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    meeting_date: datetime | None = None
    meeting_type: str | None = Field(default=None, max_length=100)
    participants: list[str] | None = None
    consent_confirmed: bool = False


class MeetingUpdate(BaseModel):
    """Partial update for meeting metadata **and** editable AI output.

    Everything is optional: only the keys actually sent are applied
    (`exclude_unset`), so the UI can patch a single field at a time.
    """

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    meeting_date: datetime | None = None
    meeting_type: str | None = Field(default=None, max_length=100)
    participants: list[str] | None = None
    # Editable AI output (human-in-the-loop)
    summary: str | None = Field(default=None, max_length=50000)
    key_points: list[str] | None = None
    risks: list[str] | None = None
    unanswered_questions: list[str] | None = None
    next_steps: list[str] | None = None
    # Meeting history
    archived: bool | None = None


class DecisionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    impact: str = Field(default="medium", pattern=r"^(low|medium|high)$")
    rationale: str | None = Field(default=None, max_length=5000)


class DecisionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    impact: str | None = Field(default=None, pattern=r"^(low|medium|high)$")
    rationale: str | None = Field(default=None, max_length=5000)
    sequence: int | None = Field(default=None, ge=0, le=10000)


class DecisionOut(BaseModel):
    id: str
    meeting_id: str
    title: str
    description: str | None = None
    impact: str
    rationale: str | None = None
    sequence: int

    model_config = {"from_attributes": True}


class TranscriptSegmentOut(BaseModel):
    id: str
    sequence: int
    start_time: float | None = None
    end_time: float | None = None
    speaker: str | None = None
    text: str
    confidence: float | None = None

    model_config = {"from_attributes": True}


class TranscriptOut(BaseModel):
    id: str
    meeting_id: str
    engine: str | None = None
    model: str | None = None
    full_text: str | None = None
    language: str | None = None
    detected_language: str | None = None
    duration_seconds: float | None = None
    completed_at: datetime | None = None
    created_at: datetime
    segments: list[TranscriptSegmentOut] = []

    model_config = {"from_attributes": True}


class MeetingSummaryOut(BaseModel):
    summary: str | None = None
    key_points: list[str] = []
    risks: list[str] = []
    unanswered_questions: list[str] = []
    next_steps: list[str] = []
    decisions: list[DecisionOut] = []


class MeetingOut(BaseModel):
    id: str
    workspace_id: str
    title: str
    description: str | None = None
    status: str
    audio_file_name: str | None = None
    audio_duration_seconds: float | None = None
    meeting_date: datetime | None = None
    meeting_type: str | None = None
    participants: list[str] | None = None
    consent_confirmed: bool
    summary: str | None = None
    key_points: list[str] | None = None
    risks: list[str] | None = None
    unanswered_questions: list[str] | None = None
    next_steps: list[str] | None = None
    error_message: str | None = None
    language: str | None = None
    archived: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MeetingOutWithDetails(MeetingOut):
    decisions: list[DecisionOut] = []
    transcript: TranscriptOut | None = None
