"""Phase 4 endpoints: the Meeting→Code agent.

Turns a meeting's decisions (and its linked tasks) into an engineering plan, then
— on a human's say-so — into the same human-in-the-loop code proposals that Dev
Studio uses. The agent never edits files itself: *applying* a plan only creates
``pending`` proposals a person must still approve.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import assert_workspace_member, get_current_user
from app.models.meeting import Decision, Meeting
from app.models.ship import CodePlan
from app.models.task import Task
from app.models.user import User
from app.schemas.ship import (
    CodePlanOut,
    PlanApplyOut,
    PlanChange,
    PlanCreateRequest,
    PlanFile,
    PlanSubtask,
)
from app.services import agent, devstudio, proposals

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

_MAX_TASKS = 50


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _meeting_dict(meeting: Meeting) -> dict:
    return {
        "title": meeting.title,
        "summary": meeting.summary,
        "key_points": list(meeting.key_points or []),
        "next_steps": list(meeting.next_steps or []),
        "meeting_date": str(meeting.meeting_date) if meeting.meeting_date else None,
    }


def _decision_dict(decision: Decision) -> dict:
    return {
        "title": decision.title,
        "description": decision.description,
        "impact": decision.impact,
        "rationale": decision.rationale,
    }


def _task_dict(task: Task) -> dict:
    return {
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
    }


def _meeting_context(meeting: Meeting | None, decisions: list[Decision]) -> str | None:
    if meeting is None:
        return None
    lines = [f"Title: {meeting.title}"]
    if meeting.summary:
        lines.append(f"Summary: {meeting.summary}")
    if decisions:
        lines.append("Decisions: " + "; ".join(f"{d.title} ({d.impact})" for d in decisions[:8]))
    return "\n".join(lines)[:4000]


def _task_context(tasks: list[Task]) -> str | None:
    if not tasks:
        return None
    return "Tasks: " + "; ".join(f"{t.title} [{t.status}]" for t in tasks[:8])


def _plan_out(plan: CodePlan) -> CodePlanOut:
    return CodePlanOut(
        id=plan.id,
        workspace_id=plan.workspace_id,
        title=plan.title,
        summary=plan.summary,
        focus=plan.focus,
        meeting_id=plan.meeting_id,
        decision_id=plan.decision_id,
        task_id=plan.task_id,
        requirements=list(plan.requirements or []),
        subtasks=[PlanSubtask(**s) for s in (plan.subtasks or []) if isinstance(s, dict)],
        affected_files=[PlanFile(**f) for f in (plan.affected_files or []) if isinstance(f, dict)],
        proposed_changes=[PlanChange(**c) for c in (plan.proposed_changes or []) if isinstance(c, dict)],
        source=plan.source,
        status=plan.status,
        proposal_ids=list(plan.proposal_ids or []),
        created_by=plan.created_by,
        created_at=plan.created_at,
    )


def _load_plan(db: Session, workspace_id: str, plan_id: str) -> CodePlan:
    plan = db.get(CodePlan, plan_id)
    if plan is None or plan.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


@router.post(
    "/workspaces/{workspace_id}/agent/plan",
    response_model=CodePlanOut,
    status_code=http_status.HTTP_201_CREATED,
)
def create_plan(
    workspace_id: str,
    payload: PlanCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CodePlanOut:
    """Turn a meeting (or a single decision) into an engineering plan."""
    assert_workspace_member(db, workspace_id, user)

    meeting: Meeting | None = None
    decisions: list[Decision] = []
    decision_id = payload.decision_id

    if payload.decision_id:
        decision = db.get(Decision, payload.decision_id)
        if decision is None:
            raise HTTPException(status_code=404, detail="Decision not found")
        parent = db.get(Meeting, decision.meeting_id)
        if parent is None or parent.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Decision not found in this workspace")
        meeting = parent
        decisions = [decision]
    elif payload.meeting_id:
        meeting = db.get(Meeting, payload.meeting_id)
        if meeting is None or meeting.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Meeting not found")
        decisions = sorted(meeting.decisions, key=lambda d: d.sequence)
    else:
        meeting = (
            db.query(Meeting)
            .filter(Meeting.workspace_id == workspace_id)
            .order_by(Meeting.created_at.desc())
            .first()
        )
        if meeting is not None:
            decisions = sorted(meeting.decisions, key=lambda d: d.sequence)

    if meeting is None and not payload.focus:
        raise HTTPException(
            status_code=400,
            detail="Nothing to plan from. Create a meeting or pass a focus instruction.",
        )

    task_query = db.query(Task).filter(Task.workspace_id == workspace_id)
    if meeting is not None:
        task_query = task_query.filter(Task.meeting_id == meeting.id)
    tasks = task_query.order_by(Task.created_at.desc()).limit(_MAX_TASKS).all()

    tree = devstudio.list_tree(workspace_id, db=db)
    result = agent.ai_code_plan(
        workspace_id,
        tree=tree,
        meeting=_meeting_dict(meeting) if meeting else None,
        decisions=[_decision_dict(d) for d in decisions],
        tasks=[_task_dict(t) for t in tasks],
        focus=payload.focus,
        db=db,
    )

    plan = CodePlan(
        workspace_id=workspace_id,
        title=result["title"],
        summary=result["summary"],
        focus=payload.focus,
        meeting_id=meeting.id if meeting else None,
        decision_id=decision_id,
        task_id=payload.task_id,
        requirements=result["requirements"],
        subtasks=result["subtasks"],
        affected_files=result["affected_files"],
        proposed_changes=result["proposed_changes"],
        source=result["source"],
        created_by=user.id,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


@router.get(
    "/workspaces/{workspace_id}/agent/plans",
    response_model=list[CodePlanOut],
)
def list_plans(
    workspace_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CodePlanOut]:
    assert_workspace_member(db, workspace_id, user)
    rows = (
        db.query(CodePlan)
        .filter(CodePlan.workspace_id == workspace_id)
        .order_by(CodePlan.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_plan_out(p) for p in rows]


@router.get(
    "/workspaces/{workspace_id}/agent/plans/{plan_id}",
    response_model=CodePlanOut,
)
def get_plan(
    workspace_id: str,
    plan_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CodePlanOut:
    assert_workspace_member(db, workspace_id, user)
    return _plan_out(_load_plan(db, workspace_id, plan_id))


@router.post(
    "/workspaces/{workspace_id}/agent/plans/{plan_id}/apply",
    response_model=PlanApplyOut,
)
def apply_plan(
    workspace_id: str,
    plan_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlanApplyOut:
    """Turn a plan's proposed changes into *pending* code proposals.

    Still human-in-the-loop: nothing reaches disk until each proposal is approved
    in Dev Studio.
    """
    assert_workspace_member(db, workspace_id, user)
    plan = _load_plan(db, workspace_id, plan_id)

    if plan.status != "draft":
        raise HTTPException(status_code=409, detail=f"This plan is already {plan.status}")

    changes = [c for c in (plan.proposed_changes or []) if isinstance(c, dict) and c.get("path")]
    if not changes:
        raise HTTPException(
            status_code=400, detail="The plan has no proposed changes to apply"
        )

    meeting = db.get(Meeting, plan.meeting_id) if plan.meeting_id else None
    decisions = sorted(meeting.decisions, key=lambda d: d.sequence) if meeting else []
    tasks = (
        db.query(Task).filter(Task.workspace_id == workspace_id, Task.meeting_id == plan.meeting_id)
        .limit(_MAX_TASKS)
        .all()
        if plan.meeting_id
        else []
    )
    meeting_ctx = _meeting_context(meeting, decisions)
    task_ctx = _task_context(tasks)

    created_ids: list[str] = []
    skipped: list[str] = []
    seen: set[str] = set()

    for change in changes:
        path = str(change.get("path"))
        if path in seen:
            continue
        seen.add(path)
        try:
            proposal = proposals.build_code_proposal(
                workspace_id,
                path,
                str(change.get("instruction") or "apply the plan"),
                meeting_id=plan.meeting_id,
                task_id=plan.task_id,
                created_by=user.id,
                meeting_context=meeting_ctx,
                task_context=task_ctx,
            )
        except proposals.ProposalError as exc:
            skipped.append(f"{path}: {exc}")
            continue
        db.add(proposal)
        db.flush()
        created_ids.append(proposal.id)

    if not created_ids:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="No proposals could be created. " + ("; ".join(skipped) if skipped else ""),
        )

    plan.status = "applied"
    plan.proposal_ids = created_ids
    db.commit()
    db.refresh(plan)

    return PlanApplyOut(
        plan=_plan_out(plan),
        created=len(created_ids),
        proposal_ids=created_ids,
        skipped=skipped,
        message=(
            f"Created {len(created_ids)} pending proposal(s). "
            "Review and approve them in Dev Studio — nothing is written yet."
        ),
    )
