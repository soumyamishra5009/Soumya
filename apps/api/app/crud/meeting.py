"""CRUD for meetings, transcripts and decisions."""

from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.meeting import Meeting, Transcript, TranscriptSegment, Decision
from app.schemas.meeting import (
    DecisionCreate,
    DecisionUpdate,
    MeetingCreate,
    MeetingUpdate,
)


class MeetingCRUD:
    def get(self, db: Session, meeting_id: str) -> Meeting | None:
        return (
            db.query(Meeting)
            .options(
                joinedload(Meeting.transcript).joinedload(Transcript.segments),
                joinedload(Meeting.decisions),
            )
            .filter(Meeting.id == meeting_id)
            .first()
        )

    def create(self, db: Session, obj_in: MeetingCreate, created_by: str | None = None) -> Meeting:
        meeting = Meeting(
            workspace_id=obj_in.workspace_id,
            created_by=created_by,
            title=obj_in.title,
            description=obj_in.description,
            meeting_date=obj_in.meeting_date,
            meeting_type=obj_in.meeting_type,
            participants=obj_in.participants,
            consent_confirmed=obj_in.consent_confirmed,
        )
        db.add(meeting)
        db.commit()
        db.refresh(meeting)
        return meeting

    def list_by_workspace(
        self,
        db: Session,
        workspace_id: str,
        skip: int = 0,
        limit: int = 50,
        q: str | None = None,
        status: str | None = None,
        archived: bool | None = None,
    ) -> list[Meeting]:
        """List meetings, defaulting to the active (non-archived) history."""
        query = db.query(Meeting).filter(Meeting.workspace_id == workspace_id)
        if q:
            needle = f"%{q.strip().lower()}%"
            query = query.filter(
                or_(
                    func.lower(Meeting.title).like(needle),
                    func.lower(func.coalesce(Meeting.description, "")).like(needle),
                )
            )
        if status:
            query = query.filter(Meeting.status == status)
        if archived is None:
            query = query.filter(Meeting.archived.is_(False))
        else:
            query = query.filter(Meeting.archived.is_(archived))
        return (
            query.order_by(Meeting.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(self, db: Session, meeting_id: str, obj_in: MeetingUpdate) -> Meeting | None:
        """Apply a partial update (meeting metadata and/or editable AI output)."""
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            return None
        data = obj_in.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(meeting, key, value)
        db.commit()
        db.refresh(meeting)
        return meeting

    def update_status(
        self, db: Session, meeting_id: str, status: str, error_message: str | None = None
    ) -> Meeting | None:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            return None
        meeting.status = status
        meeting.error_message = error_message
        db.commit()
        db.refresh(meeting)
        return meeting


class TranscriptCRUD:
    def get_by_meeting(self, db: Session, meeting_id: str) -> Transcript | None:
        return (
            db.query(Transcript)
            .options(joinedload(Transcript.segments))
            .filter(Transcript.meeting_id == meeting_id)
            .first()
        )

    def create(
        self,
        db: Session,
        meeting_id: str,
        full_text: str | None,
        engine: str | None = None,
        model: str | None = None,
        language: str | None = None,
        detected_language: str | None = None,
        duration_seconds: float | None = None,
    ) -> Transcript:
        transcript = Transcript(
            meeting_id=meeting_id,
            full_text=full_text,
            engine=engine,
            model=model,
            language=language,
            detected_language=detected_language,
            duration_seconds=duration_seconds,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(transcript)
        db.commit()
        db.refresh(transcript)
        return transcript

    def add_segments(
        self,
        db: Session,
        transcript_id: str,
        segments: list[dict],
    ) -> list[TranscriptSegment]:
        rows: list[TranscriptSegment] = []
        for seq, seg in enumerate(segments):
            row = TranscriptSegment(
                transcript_id=transcript_id,
                sequence=seq,
                start_time=seg.get("start"),
                end_time=seg.get("end"),
                speaker=seg.get("speaker"),
                text=seg.get("text", ""),
                confidence=seg.get("confidence"),
            )
            db.add(row)
            rows.append(row)
        db.commit()
        return rows


class DecisionCRUD:
    def get(self, db: Session, decision_id: str) -> Decision | None:
        return db.get(Decision, decision_id)

    def list_by_meeting(self, db: Session, meeting_id: str) -> list[Decision]:
        return (
            db.query(Decision)
            .filter(Decision.meeting_id == meeting_id)
            .order_by(Decision.sequence)
            .all()
        )

    def create(self, db: Session, meeting_id: str, obj_in: DecisionCreate) -> Decision:
        """Add a decision the AI missed (human-in-the-loop)."""
        max_seq = (
            db.query(func.max(Decision.sequence))
            .filter(Decision.meeting_id == meeting_id)
            .scalar()
        )
        row = Decision(
            meeting_id=meeting_id,
            title=obj_in.title,
            description=obj_in.description,
            impact=obj_in.impact,
            rationale=obj_in.rationale,
            sequence=(max_seq or 0) + 1,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def update(
        self, db: Session, decision_id: str, obj_in: DecisionUpdate
    ) -> Decision | None:
        row = db.get(Decision, decision_id)
        if row is None:
            return None
        data = obj_in.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return row

    def delete(self, db: Session, decision_id: str) -> bool:
        row = db.get(Decision, decision_id)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True

    def bulk_create(self, db: Session, meeting_id: str, decisions: list[dict]) -> list[Decision]:
        # Clear previous decisions for idempotency
        db.query(Decision).filter(Decision.meeting_id == meeting_id).delete()
        rows: list[Decision] = []
        for seq, item in enumerate(decisions):
            row = Decision(
                meeting_id=meeting_id,
                title=item.get("title", ""),
                description=item.get("description"),
                impact=item.get("impact", "medium"),
                rationale=item.get("rationale"),
                sequence=seq,
            )
            db.add(row)
            rows.append(row)
        db.commit()
        for row in rows:
            db.refresh(row)
        return rows


meeting = MeetingCRUD()
transcript = TranscriptCRUD()
decision = DecisionCRUD()
