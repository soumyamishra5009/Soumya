"""Meeting endpoints: create, upload, process (STT + AI summary), inspect."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    status,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.deps import get_current_user
from app.crud.meeting import (
    meeting as meeting_crud,
    transcript as transcript_crud,
    decision as decision_crud,
)
from app.crud.task import task as task_crud
from app.schemas.meeting import (
    DecisionCreate,
    DecisionOut,
    DecisionUpdate,
    MeetingCreate,
    MeetingOut,
    MeetingOutWithDetails,
    MeetingSummaryOut,
    MeetingUpdate,
)
from app.schemas.task import TaskOut
from app.models.user import User
from app.models.workspace import Workspace
from app.models.meeting import Meeting
from app.models.enums import MeetingStatus, TaskPriority
from app.services import audio, stt, storage
from app.services.meeting_summary import extract_meeting_intelligence
from app.services.storage import validate_filename

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meetings"])


def _process_meeting_background(meeting_id: str) -> None:
    """Transcribe + summarize a meeting. Runs outside the request cycle.

    Uses a fresh DB session because BackgroundTasks outlive the request.
    """
    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or not meeting.audio_file_path:
            return

        # 1) Transcription
        meeting.status = MeetingStatus.TRANSCRIBING.value
        db.commit()

        try:
            result = stt.transcribe_with_fallback(meeting.audio_file_path)
        except Exception as exc:
            logger.exception("Transcription failed for %s", meeting_id)
            meeting.status = MeetingStatus.FAILED.value
            meeting.error_message = f"Transcription failed: {exc}"
            db.commit()
            return

        transcript = transcript_crud.create(
            db,
            meeting_id=meeting_id,
            full_text=result.get("full_text") or "",
            engine=result.get("engine"),
            model=result.get("model"),
            language=result.get("language"),
            detected_language=result.get("language"),
            duration_seconds=result.get("duration_seconds"),
        )
        if result.get("segments"):
            transcript_crud.add_segments(db, transcript.id, result["segments"])

        meeting.language = result.get("language")
        meeting.transcribed_by = result.get("engine")
        if result.get("duration_seconds"):
            meeting.audio_duration_seconds = result.get("duration_seconds")

        # 2) AI summary + decisions + action items
        meeting.status = MeetingStatus.SUMMARIZING.value
        db.commit()

        full_text = result.get("full_text") or ""
        if not full_text.strip():
            meeting.status = MeetingStatus.FAILED.value
            meeting.error_message = "Transcription produced empty text"
            db.commit()
            return

        try:
            intel = extract_meeting_intelligence(
                transcript_text=full_text,
                title=meeting.title,
                meeting_date=meeting.meeting_date.isoformat() if meeting.meeting_date else None,
                participants=meeting.participants,
            )
        except Exception as exc:
            logger.exception("Summary failed for %s", meeting_id)
            meeting.status = MeetingStatus.FAILED.value
            meeting.error_message = f"AI summary failed: {exc}"
            db.commit()
            return

        summary_text = intel.get("summary") or None
        if intel.get("source") == "fallback" and summary_text:
            summary_text = (
                "⚠️ Offline extractive summary — no LLM was reachable, so this "
                "was generated with local heuristics. Start Ollama or set an "
                "OpenRouter key for AI-quality results.\n\n" + summary_text
            )
        meeting.summary = summary_text
        meeting.key_points = intel.get("key_points") or []
        meeting.risks = intel.get("risks") or []
        meeting.unanswered_questions = intel.get("unanswered_questions") or []
        meeting.next_steps = intel.get("next_steps") or []
        db.commit()

        # Persist decisions
        decision_crud.bulk_create(db, meeting_id, intel.get("decisions") or [])

        # Persist action items as tasks linked to this meeting
        action_items = intel.get("action_items") or []
        if action_items:
            priority_rank = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
            action_items = sorted(
                action_items,
                key=lambda x: priority_rank.get(x.get("priority", "medium"), 2),
            )
            for idx, item in enumerate(action_items):
                due = item.get("due_date")
                if due:
                    try:
                        item["due_date"] = datetime.strptime(due, "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                    except ValueError:
                        item["due_date"] = None
                if item.get("priority") not in {p.value for p in TaskPriority}:
                    item["priority"] = TaskPriority.MEDIUM.value
                item.setdefault("sequence", idx)
            task_crud.bulk_create_from_meeting(
                db,
                workspace_id=meeting.workspace_id,
                meeting_id=meeting_id,
                items=action_items,
                reporter_id=meeting.created_by,
            )

        meeting.status = MeetingStatus.COMPLETED.value
        meeting.error_message = None
        db.commit()
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected failure processing meeting %s", meeting_id)
        try:
            m = db.get(Meeting, meeting_id)
            if m is not None:
                m.status = MeetingStatus.FAILED.value
                m.error_message = str(exc)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _assert_member(db: Session, workspace_id: str, user: User) -> Workspace:
    from app.models.workspace import WorkspaceMember

    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )
    if member is None and workspace.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return workspace


@router.post("/meetings", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def create_meeting(
    payload: MeetingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Meeting:
    _assert_member(db, payload.workspace_id, user)
    return meeting_crud.create(db, obj_in=payload, created_by=user.id)


@router.get("/workspaces/{workspace_id}/meetings", response_model=list[MeetingOut])
def list_meetings(
    workspace_id: str,
    q: str | None = Query(default=None, description="Search title and description."),
    meeting_status: str | None = None,
    archived: bool | None = Query(
        default=None,
        description="None returns active meetings; true returns only archived ones.",
    ),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Meeting]:
    _assert_member(db, workspace_id, user)
    return meeting_crud.list_by_workspace(
        db,
        workspace_id,
        skip=skip,
        limit=min(limit, 200),
        q=q,
        status=meeting_status,
        archived=archived,
    )


@router.get("/meetings/{meeting_id}", response_model=MeetingOutWithDetails)
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Meeting:
    meeting = meeting_crud.get(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)
    return meeting


@router.patch("/meetings/{meeting_id}", response_model=MeetingOut)
def update_meeting(
    meeting_id: str,
    payload: MeetingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Meeting:
    """Edit meeting metadata and/or the AI output (human-in-the-loop)."""
    meeting = meeting_crud.get(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)

    updated = meeting_crud.update(db, meeting_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return updated


@router.post(
    "/meetings/{meeting_id}/decisions",
    response_model=DecisionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_decision(
    meeting_id: str,
    payload: DecisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Decision:
    """Record a decision the AI missed."""
    meeting = meeting_crud.get(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)
    return decision_crud.create(db, meeting_id, payload)


@router.patch("/decisions/{decision_id}", response_model=DecisionOut)
def update_decision(
    decision_id: str,
    payload: DecisionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Decision:
    decision = decision_crud.get(db, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    meeting = meeting_crud.get(db, decision.meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)

    updated = decision_crud.update(db, decision_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return updated


@router.delete("/decisions/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_decision(
    decision_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    decision = decision_crud.get(db, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    meeting = meeting_crud.get(db, decision.meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)

    decision_crud.delete(db, decision_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/meetings/{meeting_id}/audio", response_model=MeetingOut)
async def upload_audio(
    meeting_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Meeting:
    meeting = meeting_crud.get(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)

    if not validate_filename(file.filename or ""):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Use mp3, wav, m4a, flac, ogg, webm, mp4.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        path = storage.save_audio(data, file.filename or "upload")
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    meeting.audio_file_path = path
    meeting.audio_file_name = file.filename
    meeting.audio_mime_type = file.content_type
    meeting.audio_size_bytes = len(data)
    # Probe duration now so the UI can show it before transcription finishes.
    duration = audio.probe_duration_seconds(path)
    if duration:
        meeting.audio_duration_seconds = duration
    meeting.status = MeetingStatus.UPLOADING.value
    meeting.error_message = None
    db.commit()
    db.refresh(meeting)
    return meeting


@router.post("/meetings/{meeting_id}/process", response_model=MeetingOut)
def process_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Meeting:
    """Kick off transcription + AI summary in the background."""
    meeting = meeting_crud.get(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)

    if not meeting.audio_file_path:
        raise HTTPException(status_code=400, detail="Upload audio first")
    if not meeting.consent_confirmed:
        raise HTTPException(status_code=400, detail="Participant consent not confirmed")

    meeting.status = MeetingStatus.TRANSCRIBING.value
    meeting.error_message = None
    db.commit()
    db.refresh(meeting)

    background_tasks.add_task(_process_meeting_background, meeting_id)
    return meeting


@router.get("/meetings/{meeting_id}/summary", response_model=MeetingSummaryOut)
def get_meeting_summary(
    meeting_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeetingSummaryOut:
    meeting = meeting_crud.get(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)

    decisions = decision_crud.list_by_meeting(db, meeting_id)
    return MeetingSummaryOut(
        summary=meeting.summary,
        key_points=meeting.key_points or [],
        risks=meeting.risks or [],
        unanswered_questions=meeting.unanswered_questions or [],
        next_steps=meeting.next_steps or [],
        decisions=decisions,
    )


@router.get("/meetings/{meeting_id}/tasks", response_model=list[TaskOut])
def list_meeting_tasks(
    meeting_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list:
    meeting = meeting_crud.get(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)
    return task_crud.list_by_meeting(db, meeting_id)


@router.get("/meetings/{meeting_id}/audio")
def stream_meeting_audio(
    meeting_id: str,
    token: str | None = Query(default=None, description="JWT (for <audio> tags)"),
    db: Session = Depends(get_db),
):
    """Stream the uploaded recording.

    Accepts the bearer token either via the Authorization header (normal API
    clients) or a `?token=` query parameter, since HTML <audio> elements cannot
    set custom headers.
    """
    user: User | None = None
    if token:
        from app.core.security import decode_access_token

        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            user = db.get(User, payload["sub"])
    if user is None:
        # Fall back to the standard header-based dependency
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid audio token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    meeting = meeting_crud.get(db, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _assert_member(db, meeting.workspace_id, user)

    if not meeting.audio_file_path or not os.path.exists(meeting.audio_file_path):
        raise HTTPException(status_code=404, detail="Audio file not available")

    return FileResponse(
        meeting.audio_file_path,
        media_type=meeting.audio_mime_type or "application/octet-stream",
        filename=meeting.audio_file_name or os.path.basename(meeting.audio_file_path),
    )

