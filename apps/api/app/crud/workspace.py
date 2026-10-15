"""CRUD for workspaces and membership."""

import re

from sqlalchemy.orm import Session

from app.models.workspace import Workspace, WorkspaceMember
from app.models.enums import WorkspaceRole
from app.schemas.workspace import WorkspaceCreate


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "workspace"


class WorkspaceCRUD:
    def get(self, db: Session, workspace_id: str) -> Workspace | None:
        return db.get(Workspace, workspace_id)

    def create(
        self, db: Session, obj_in: WorkspaceCreate, owner_id: str
    ) -> Workspace:
        base_slug = obj_in.slug or slugify(obj_in.name)
        slug = base_slug
        counter = 1
        while (
            db.query(Workspace).filter(Workspace.slug == slug).first() is not None
        ):
            slug = f"{base_slug}-{counter}"
            counter += 1

        workspace = Workspace(
            name=obj_in.name,
            description=obj_in.description,
            slug=slug,
            owner_id=owner_id,
        )
        db.add(workspace)
        db.flush()

        # Add owner as a member
        db.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=owner_id,
                role=WorkspaceRole.OWNER.value,
            )
        )
        db.commit()
        db.refresh(workspace)
        return workspace

    def list_for_user(self, db: Session, user_id: str) -> list[Workspace]:
        return (
            db.query(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .filter(WorkspaceMember.user_id == user_id)
            .filter(Workspace.is_active.is_(True))
            .order_by(Workspace.created_at.desc())
            .all()
        )

    def add_member(
        self, db: Session, workspace_id: str, user_id: str, role: str = WorkspaceRole.MEMBER.value
    ) -> WorkspaceMember:
        existing = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
            .first()
        )
        if existing:
            return existing
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        db.add(member)
        db.commit()
        db.refresh(member)
        return member


workspace = WorkspaceCRUD()
