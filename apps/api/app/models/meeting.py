from sqlalchemy import (
    String, Boolean, DateTime, Text, ForeignKey, JSON, Integer, Float, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone

from app.models.base import Base, generate_uuid
from app.models.enums import MeetingStatus, DecisionImpact


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default=MeetingStatus.PENDING.value, nullable=False, index=True
    )

    # Media
    audio_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Meeting meta
    meeting_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    participants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # AI-extracted summary
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    risks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    unanswered_questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    next_steps: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Meeting history: archived meetings are hidden from the default list
    archived: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    # Error handling
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Transcription meta
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    transcribed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="meetings")
    transcript = relationship(
        "Transcript", back_populates="meeting", uselist=False, cascade="all, delete-orphan"
    )
    decisions = relationship("Decision", back_populates="meeting", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="meeting", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Meeting {self.title} [{self.status}]>"


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )

    engine: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )

    meeting = relationship("Meeting", back_populates="transcript")
    segments = relationship(
        "TranscriptSegment", back_populates="transcript",
        order_by="TranscriptSegment.sequence",
        cascade="all, delete-orphan",
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    transcript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    start_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    speaker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    transcript = relationship("Transcript", back_populates="segments")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, index=True
    )
    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact: Mapped[str] = mapped_column(
        String(20), default=DecisionImpact.MEDIUM.value, nullable=False
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False
    )

    meeting = relationship("Meeting", back_populates="decisions")
    tasks = relationship("Task", back_populates="decision", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Decision {self.title}>"