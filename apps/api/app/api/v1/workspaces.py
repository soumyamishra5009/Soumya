"""Workspace endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_member
from app.crud.workspace import workspace as workspace_crud
from app.schemas.workspace import WorkspaceCreate, WorkspaceOut
from app.models.user import User
from app.models.workspace import Workspace

router = APIRouter(tags=["workspaces"])


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Workspace:
    workspace = workspace_crud.create(db, obj_in=payload, owner_id=user.id)
    return workspace


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Workspace]:
    return workspace_crud.list_for_user(db, user.id)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace: Workspace = Depends(require_workspace_member),
) -> Workspace:
    return workspace
