"""Task endpoints: CRUD + filterable Kanban listing."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.task import task as task_crud
from app.crud.workspace import workspace as workspace_crud
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut
from app.models.user import User
from app.models.task import Task
from app.models.workspace import Workspace, WorkspaceMember

router = APIRouter(tags=["tasks"])


def _assert_member(db: Session, workspace_id: str, user: User) -> Workspace:
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


def _assert_assignee(db: Session, workspace_id: str, assignee_id: str | None) -> None:
    """Guard against assigning work to someone outside the workspace."""
    if not assignee_id:
        return
    if db.get(User, assignee_id) is None:
        raise HTTPException(status_code=404, detail="Assignee not found")
    if workspace_crud.get_member(db, workspace_id, assignee_id) is None:
        workspace = db.get(Workspace, workspace_id)
        if workspace is None or workspace.owner_id != assignee_id:
            raise HTTPException(
                status_code=400, detail="Assignee is not a member of this workspace"
            )


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Task:
    _assert_member(db, payload.workspace_id, user)
    _assert_assignee(db, payload.workspace_id, payload.assignee_id)
    return task_crud.create(db, obj_in=payload, reporter_id=user.id)


@router.get("/workspaces/{workspace_id}/tasks", response_model=list[TaskOut])
def list_tasks(
    workspace_id: str,
    task_status: str | None = None,
    assignee_id: str | None = Query(
        default=None,
        description='Filter by assignee user id, or the special values "me" / "unassigned".',
    ),
    priority: str | None = None,
    q: str | None = Query(default=None, description="Search title and description."),
    meeting_id: str | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Task]:
    _assert_member(db, workspace_id, user)

    resolved_assignee: str | None = None
    unassigned = False
    if assignee_id == "me":
        resolved_assignee = user.id
    elif assignee_id == "unassigned":
        unassigned = True
    elif assignee_id:
        resolved_assignee = assignee_id

    return task_crud.list_by_workspace(
        db,
        workspace_id,
        status=task_status,
        assignee_id=resolved_assignee,
        unassigned=unassigned,
        priority=priority,
        q=q,
        meeting_id=meeting_id,
        due_before=due_before,
        due_after=due_after,
        skip=skip,
        limit=min(limit, 500),
    )


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Task:
    task = task_crud.get(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_member(db, task.workspace_id, user)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Task:
    task = task_crud.get(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    _assert_member(db, task.workspace_id, user)

    if "assignee_id" in payload.model_fields_set:
        _assert_assignee(db, task.workspace_id, payload.assignee_id)

    updated = task_crud.update(db, task_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated
