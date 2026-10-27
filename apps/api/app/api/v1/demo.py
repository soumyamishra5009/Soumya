from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.core.database import SessionLocal
from app.core.deps import get_current_user
from app.models.meeting import Meeting
from app.models.task import Task
from app.models.user import User
from app.models.workspace import Workspace

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed")
async def seed_demo_data(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Seed demo workspace with sample meeting, decisions, and tasks."""
    db = SessionLocal()
    try:
        ws = db.query(Workspace).filter(Workspace.owner_id == current_user.id).first()
        if not ws:
            ws = Workspace(
                id=str(uuid.uuid4()),
                name="Demo Workspace",
                description="Auto-seeded demo workspace for Cognix AI",
                owner_id=current_user.id,
            )
            db.add(ws)
            db.commit()
            db.refresh(ws)

        # Check if demo meeting exists
        existing = db.query(Meeting).filter(Meeting.workspace_id == ws.id, Meeting.title.contains("Demo")).first()
        if existing:
            return {"status": "exists", "workspace_id": ws.id, "meeting_id": existing.id}

        meeting_id = str(uuid.uuid4())
        now = datetime.utcnow()
        transcript = """[00:00] Alice: Okay team, let's align on the Cognix dashboard for this sprint.
[00:15] Bob: We need to fix the divide by zero bug in calculator.py - it's crashing on edge cases.
[00:35] Alice: Also add proper error handling for API calls in the frontend.
[00:55] Carol: Let's add unit tests for the calculator module before merging.
[01:15] Bob: We should also improve the Kanban board UX - add due date validation.
[01:40] Alice: Decision: We'll ship these fixes by EOD Friday. Bob will handle backend fixes, Carol handles tests.
[02:00] Carol: Action item - update README with setup instructions.
"""

        decisions = [
            {
                "id": str(uuid.uuid4()),
                "text": "Fix divide by zero bug in calculator.py and add error handling",
                "owner": "Bob",
                "status": "open",
                "source": "transcript",
            },
            {
                "id": str(uuid.uuid4()),
                "text": "Add unit tests for calculator module",
                "owner": "Carol",
                "status": "open",
                "source": "transcript",
            },
            {
                "id": str(uuid.uuid4()),
                "text": "Improve Kanban board UX with due date validation",
                "owner": "Bob",
                "status": "open",
                "source": "transcript",
            },
        ]

        action_items = [
            {"id": str(uuid.uuid4()), "text": "Fix divide by zero bug in calculator.py", "assignee": "Bob", "status": "todo"},
            {"id": str(uuid.uuid4()), "text": "Add unit tests for calculator module", "assignee": "Carol", "status": "todo"},
            {"id": str(uuid.uuid4()), "text": "Improve Kanban board UX", "assignee": "Bob", "status": "todo"},
            {"id": str(uuid.uuid4()), "text": "Update README with setup instructions", "assignee": "Carol", "status": "todo"},
        ]

        meeting = Meeting(
            id=meeting_id,
            workspace_id=ws.id,
            title="Demo Sprint Planning Meeting",
            transcript=transcript,
            summary="Team aligned on sprint priorities: fix calculator bug, add tests, improve Kanban UX. Tasks assigned with deadlines.",
            key_points=json.dumps(["Fix divide by zero bug", "Add unit tests", "Improve Kanban UX", "Update README"]),
            decisions=json.dumps(decisions),
            risks=json.dumps(["Calculator crashes could affect demos", "Need to ensure tests pass before merge"]),
            questions=json.dumps(["Do we need backward compatibility?"]),
            action_items=json.dumps(action_items),
            status="processed",
            created_at=now,
            updated_at=now,
        )
        db.add(meeting)

        # Create tasks from action items
        for ai in action_items:
            task = Task(
                id=str(uuid.uuid4()),
                workspace_id=ws.id,
                meeting_id=meeting_id,
                title=ai["text"],
                description=f"Auto-generated from Demo Sprint Planning Meeting. Assignee: {ai['assignee']}",
                status=ai["status"],
                priority="high" if "bug" in ai["text"].lower() else "medium",
                assignee_id=current_user.id,
                created_at=now,
                due_date=(now + timedelta(days=2)).date() if "bug" in ai["text"].lower() else (now + timedelta(days=3)).date(),
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
