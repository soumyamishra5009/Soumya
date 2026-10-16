"""Workspace endpoints: workspaces + team membership."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_member
from app.crud.workspace import workspace as workspace_crud
from app.models.enums import WorkspaceRole
from app.schemas.workspace import (
    MemberAdd,
    MemberOut,
    WorkspaceCreate,
    WorkspaceOut,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

router = APIRouter(tags=["workspaces"])

_MANAGER_ROLES = {WorkspaceRole.OWNER.value, WorkspaceRole.ADMIN.value}


def _role_for(db: Session, workspace: Workspace, user: User) -> str:
    member = workspace_crud.get_member(db, workspace.id, user.id)
    if member is not None:
        return member.role
    return WorkspaceRole.OWNER.value if workspace.owner_id == user.id else ""


def _require_manager(db: Session, workspace: Workspace, user: User) -> None:
    if _role_for(db, workspace, user) not in _MANAGER_ROLES:
        raise HTTPException(
            status_code=403, detail="Only workspace owners or admins can manage members"
        )


def _to_member_out(workspace: Workspace, member: WorkspaceMember, user: User) -> MemberOut:
    return MemberOut(
        membership_id=member.id,
        user_id=user.id,
        name=user.name,
        email=user.email,
        image=user.image,
        role=member.role,
        is_owner=workspace.owner_id == user.id,
        accepted_at=member.accepted_at,
        invited_at=member.invited_at,
    )


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


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_members(
    workspace: Workspace = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    rows = workspace_crud.list_members(db, workspace.id)
    return [_to_member_out(workspace, member, user) for member, user in rows]


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    payload: MemberAdd,
    workspace: Workspace = Depends(require_workspace_member),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemberOut:
    """Attach an existing SyncForge account to this workspace by email.

    We deliberately do not create accounts on someone else's behalf — the
    invitee must sign up first, then be added here.
    """
    _require_manager(db, workspace, user)

    invitee = (
        db.query(User)
        .filter(func.lower(User.email) == payload.email.strip().lower())
        .first()
    )
    if invitee is None:
        raise HTTPException(
            status_code=404,
            detail="No SyncForge account with that email. Ask them to sign up first.",
        )
    if invitee.id == workspace.owner_id:
        raise HTTPException(status_code=409, detail="That user already owns this workspace")
    if workspace_crud.get_member(db, workspace.id, invitee.id) is not None:
        raise HTTPException(status_code=409, detail="Already a member of this workspace")

    member = workspace_crud.add_member(
        db, workspace_id=workspace.id, user_id=invitee.id, role=payload.role
    )
    return _to_member_out(workspace, member, invitee)


@router.delete(
    "/workspaces/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    user_id: str,
    workspace: Workspace = Depends(require_workspace_member),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    _require_manager(db, workspace, user)
    if user_id == workspace.owner_id:
        raise HTTPException(status_code=400, detail="The workspace owner cannot be removed")

    if not workspace_crud.remove_member(db, workspace.id, user_id):
        raise HTTPException(status_code=404, detail="Member not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
