"""Task endpoints: CRUD + Kanban-style listing."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.task import task as task_crud
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


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Task:
    _assert_member(db, payload.workspace_id, user)
    return task_crud.create(db, obj_in=payload, reporter_id=user.id)


@router.get("/workspaces/{workspace_id}/tasks", response_model=list[TaskOut])
def list_tasks(
    workspace_id: str,
    task_status: str | None = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Task]:
    _assert_member(db, workspace_id, user)
    return task_crud.list_by_workspace(
        db, workspace_id, status=task_status, skip=skip, limit=min(limit, 500)
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

    updated = task_crud.update(db, task_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated
