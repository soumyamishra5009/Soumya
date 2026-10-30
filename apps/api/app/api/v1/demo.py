from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.database import SessionLocal
from app.core.deps import get_current_user
from app.crud.workspace import WorkspaceCRUD
from app.models.enums import DecisionImpact, MeetingStatus, TaskPriority, TaskStatus
from app.models.meeting import Decision, Meeting, Transcript
from app.models.task import Task
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed")
async def seed_demo_data(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Seed demo workspace with sample meeting, decisions, and tasks."""
    db = SessionLocal()
    try:
        ws = db.query(Workspace).filter(Workspace.owner_id == current_user.id).first()
        if not ws:
            # Reuse the CRUD path so the workspace gets a unique slug and the
            # owner is added as a member (both are required elsewhere).
            ws = WorkspaceCRUD().create(
                db,
                WorkspaceCreate(
                    name="Demo Workspace",
                    description="Auto-seeded demo workspace for Cognix AI",
                ),
                current_user.id,
            )

        # Check if demo meeting exists
        existing = db.query(Meeting).filter(Meeting.workspace_id == ws.id, Meeting.title.contains("Demo")).first()
        if existing:
            return {
                "status": "exists",
                "workspace_id": ws.id,
                "meeting_id": existing.id,
                "tasks_created": 0,
                "message": "Demo data already exists in this workspace.",
            }

        meeting_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        transcript_text = """[00:00] Alice: Okay team, let's align on the Cognix dashboard for this sprint.
[00:15] Bob: We need to fix the divide by zero bug in calculator.py - it's crashing on edge cases.
[00:35] Alice: Also add proper error handling for API calls in the frontend.
[00:55] Carol: Let's add unit tests for the calculator module before merging.
[01:15] Bob: We should also improve the Kanban board UX - add due date validation.
[01:40] Alice: Decision: We'll ship these fixes by EOD Friday. Bob will handle backend fixes, Carol handles tests.
[02:00] Carol: Action item - update README with setup instructions.
"""

        decisions = [
            Decision(
                id=str(uuid.uuid4()),
                title="Fix divide by zero bug in calculator.py",
                description="Add explicit error handling for edge cases and cover them with tests.",
                impact=DecisionImpact.HIGH.value,
                rationale="Bob reported crashes on edge cases during the demo.",
                sequence=0,
            ),
            Decision(
                id=str(uuid.uuid4()),
                title="Add unit tests for the calculator module",
                description="Write tests before merging the bug fix.",
                impact=DecisionImpact.MEDIUM.value,
                rationale="Carol owns test coverage for this module.",
                sequence=1,
            ),
            Decision(
                id=str(uuid.uuid4()),
                title="Improve Kanban board UX with due date validation",
                description="Validate due dates and show overdue tasks clearly.",
                impact=DecisionImpact.MEDIUM.value,
                rationale="Raised as a follow-up improvement for the task board.",
                sequence=2,
            ),
        ]

        action_items = [
            {"text": "Fix divide by zero bug in calculator.py", "assignee": "Bob", "status": TaskStatus.TODO.value},
            {"text": "Add unit tests for calculator module", "assignee": "Carol", "status": TaskStatus.IN_PROGRESS.value},
            {"text": "Improve Kanban board UX", "assignee": "Bob", "status": TaskStatus.TODO.value},
            {"text": "Update README with setup instructions", "assignee": "Carol", "status": TaskStatus.TODO.value},
        ]

        meeting = Meeting(
            id=meeting_id,
            workspace_id=ws.id,
            created_by=current_user.id,
            title="Demo Sprint Planning Meeting",
            description="Seeded meeting used by the one-click demo flow.",
            transcript=Transcript(
                id=str(uuid.uuid4()),
                full_text=transcript_text,
                engine="demo-seed",
                language="en",
                completed_at=now,
            ),
            participants=["Alice", "Bob", "Carol"],
            meeting_type="sprint_planning",
            meeting_date=now,
            consent_confirmed=True,
            summary="Team aligned on sprint priorities: fix calculator bug, add tests, improve Kanban UX. Tasks assigned with deadlines.",
            key_points=["Fix divide by zero bug", "Add unit tests", "Improve Kanban UX", "Update README"],
            risks=["Calculator crashes could affect demos", "Need to ensure tests pass before merge"],
            unanswered_questions=["Do we need backward compatibility?"],
            next_steps=["Ship the fixes by EOD Friday", "Review test coverage before merge"],
            decisions=decisions,
            status=MeetingStatus.COMPLETED.value,
            language="en",
            transcribed_by="demo-seed",
            created_at=now,
            updated_at=now,
        )
        db.add(meeting)

        # Create tasks from action items
        for index, ai in enumerate(action_items):
            is_urgent = "bug" in ai["text"].lower()
            task = Task(
                id=str(uuid.uuid4()),
                workspace_id=ws.id,
                meeting_id=meeting_id,
                title=ai["text"],
                description=f"Auto-generated from Demo Sprint Planning Meeting. Assignee: {ai['assignee']}",
                status=ai["status"],
                priority=TaskPriority.HIGH.value if is_urgent else TaskPriority.MEDIUM.value,
                assignee_id=current_user.id,
                sequence=index,
                created_at=now,
                due_date=now + timedelta(days=2 if is_urgent else 3),
            )
            db.add(task)

        db.commit()
        return {
            "status": "created",
            "workspace_id": ws.id,
            "meeting_id": meeting_id,
            "tasks_created": len(action_items),
            "message": "Demo data seeded successfully!",
        }
    finally:
        db.close()
