"""Phase 5 endpoints: sandboxed test runs (verification).

A run executes the workspace's tests inside its Dev Studio sandbox and records
the result. It never touches the host project and it is the evidence a human
reviews before shipping a pull request.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import assert_workspace_member, get_current_user
from app.models.user import User
from app.models.verify import TestRun
from app.schemas.verify import TestRunOut, TestRunRequest
from app.services import testrunner

logger = logging.getLogger(__name__)

router = APIRouter(tags=["verify"])


def _run_out(run: TestRun) -> TestRunOut:
    return TestRunOut(
        id=run.id,
        workspace_id=run.workspace_id,
        kind=run.kind,
        runner=run.runner,
        command=run.command,
        target=run.target,
        status=run.status,
        exit_code=run.exit_code,
        passed=run.passed,
        failed=run.failed,
        errors=run.errors,
        duration_ms=run.duration_ms,
        output=run.output,
        output_truncated=run.output_truncated,
        source=run.source,
        created_by=run.created_by,
        created_at=run.created_at,
        summary=testrunner.summarise({
            "status": run.status,
            "passed": run.passed,
            "failed": run.failed,
        }),
    )


def _load_run(db: Session, workspace_id: str, run_id: str) -> TestRun:
    run = db.get(TestRun, run_id)
    if run is None or run.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Test run not found")
    return run


@router.post(
    "/workspaces/{workspace_id}/tests/run",
    response_model=TestRunOut,
    status_code=http_status.HTTP_201_CREATED,
)
def run_tests(
    workspace_id: str,
    payload: TestRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TestRunOut:
    """Execute the workspace's tests in the sandbox and store the result."""
    assert_workspace_member(db, workspace_id, user)

    try:
        result = testrunner.run_tests(
            workspace_id,
            kind=payload.kind,
            target=payload.target,
            timeout=payload.timeout,
            prefer_pytest=payload.prefer_pytest,
        )
    except testrunner.TestRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    run = TestRun(
        workspace_id=workspace_id,
        kind=result["kind"],
        runner=result["runner"],
        command=result["command"],
        target=result["target"],
        status=result["status"],
        exit_code=result["exit_code"],
        passed=result["passed"],
        failed=result["failed"],
        errors=result["errors"],
        duration_ms=result["duration_ms"],
        output=result["output"],
        output_truncated=result["output_truncated"],
        source=result["source"],
        created_by=user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _run_out(run)


@router.get(
    "/workspaces/{workspace_id}/tests",
    response_model=list[TestRunOut],
)
def list_runs(
    workspace_id: str,
    run_status: str | None = Query(
        default=None, alias="status", description="passed | failed | error | timeout"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TestRunOut]:
    assert_workspace_member(db, workspace_id, user)
    query = db.query(TestRun).filter(TestRun.workspace_id == workspace_id)
    if run_status:
        query = query.filter(TestRun.status == run_status)
    rows = query.order_by(TestRun.created_at.desc()).limit(limit).all()
    return [_run_out(r) for r in rows]


@router.get(
    "/workspaces/{workspace_id}/tests/latest",
    response_model=TestRunOut,
)
def latest_run(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TestRunOut:
    assert_workspace_member(db, workspace_id, user)
    run = (
        db.query(TestRun)
        .filter(TestRun.workspace_id == workspace_id)
        .order_by(TestRun.created_at.desc())
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="No test runs yet")
    return _run_out(run)


@router.get(
    "/workspaces/{workspace_id}/tests/{run_id}",
    response_model=TestRunOut,
)
def get_run(
    workspace_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TestRunOut:
    assert_workspace_member(db, workspace_id, user)
    return _run_out(_load_run(db, workspace_id, run_id))


@router.delete(
    "/workspaces/{workspace_id}/tests/{run_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
def delete_run(
    workspace_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    assert_workspace_member(db, workspace_id, user)
    run = _load_run(db, workspace_id, run_id)
    db.delete(run)
    db.commit()
