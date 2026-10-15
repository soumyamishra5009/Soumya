"""CRUD for tasks."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


class TaskCRUD:
    def get(self, db: Session, task_id: str) -> Task | None:
        return db.get(Task, task_id)

    def create(self, db: Session, obj_in: TaskCreate, reporter_id: str | None = None) -> Task:
        task = Task(
            workspace_id=obj_in.workspace_id,
            title=obj_in.title,
            description=obj_in.description,
            status=obj_in.status,
            priority=obj_in.priority,
            assignee_id=obj_in.assignee_id,
            reporter_id=reporter_id,
            meeting_id=obj_in.meeting_id,
            decision_id=obj_in.decision_id,
            due_date=obj_in.due_date,
            start_date=obj_in.start_date,
            estimated_hours=obj_in.estimated_hours,
            tags=obj_in.tags,
            sequence=obj_in.sequence,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def bulk_create_from_meeting(
        self, db: Session, workspace_id: str, meeting_id: str,
        items: list[dict], reporter_id: str | None = None,
    ) -> list[Task]:
        # Idempotent: regenerate tasks derived from this meeting on re-process
        db.query(Task).filter(Task.meeting_id == meeting_id).delete(synchronize_session=False)
        tasks: list[Task] = []
        for seq, item in enumerate(items):
            task = Task(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                decision_id=item.get("decision_id"),
                title=item.get("title", ""),
                description=item.get("description"),
                priority=item.get("priority", "medium"),
                assignee_id=item.get("assignee_id"),
                due_date=item.get("due_date"),
                estimated_hours=item.get("estimated_hours"),
                reporter_id=reporter_id,
                status="todo",
                sequence=seq,
            )
            db.add(task)
            tasks.append(task)
        db.commit()
        for t in tasks:
            db.refresh(t)
        return tasks

    def update(self, db: Session, task_id: str, obj_in: TaskUpdate) -> Task | None:
        task = db.get(Task, task_id)
        if task is None:
            return None
        data = obj_in.model_dump(exclude_unset=True)
        if "status" in data and data["status"] == "done" and task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)
        elif "status" in data and data["status"] != "done":
            task.completed_at = None
        for key, value in data.items():
            setattr(task, key, value)
        db.commit()
        db.refresh(task)
        return task

    def list_by_workspace(
        self, db: Session, workspace_id: str,
        status: str | None = None, skip: int = 0, limit: int = 200,
    ) -> list[Task]:
        query = db.query(Task).filter(Task.workspace_id == workspace_id)
        if status:
            query = query.filter(Task.status == status)
        return (
            query.order_by(Task.sequence, Task.created_at)
            .offset(skip).limit(limit).all()
        )

    def list_by_meeting(self, db: Session, meeting_id: str) -> list[Task]:
        return (
            db.query(Task)
            .filter(Task.meeting_id == meeting_id)
            .order_by(Task.sequence, Task.created_at)
            .all()
        )


task = TaskCRUD()
