"""Activity log: every approved change, who approved it, what happened and what it saved."""

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.auth import require_admin
from app.db import get_session
from app.engine.forecaster import group_demand
from app.jobs.engine_run import metrics_frame
from app.models import ActionLog, Group, Recommendation, Server, as_utc, utcnow

router = APIRouter(prefix="/api/actions", tags=["actions"], dependencies=[Depends(require_admin)])


class ActionOut(BaseModel):
    """One action log entry with the change it made."""

    id: int
    recommendation_id: int
    group_id: Optional[int]
    group_name: Optional[str]
    kind: Optional[str]
    from_count: Optional[int]
    to_count: Optional[int]
    status: Optional[str]
    approved_by: str
    approved_at: datetime
    executed_at: Optional[datetime]
    finished_at: Optional[datetime]
    result: Optional[str]
    details: dict[str, Any]
    realized_savings_inr: float


def action_out(db: Session, action: ActionLog) -> ActionOut:
    """Convert an action row (plus its recommendation) to the response model."""
    assert action.id is not None
    rec = db.get(Recommendation, action.recommendation_id)
    group = db.get(Group, rec.group_id) if rec else None
    try:
        details = json.loads(action.details_json or "{}")
    except json.JSONDecodeError:
        details = {}
    return ActionOut(
        id=action.id, recommendation_id=action.recommendation_id, group_id=rec.group_id if rec else None,
        group_name=group.name if group else None, kind=rec.kind if rec else None,
        from_count=rec.from_count if rec else None, to_count=rec.to_count if rec else None,
        status=rec.status if rec else None, approved_by=action.approved_by, approved_at=action.approved_at,
        executed_at=action.executed_at, finished_at=action.finished_at, result=action.result, details=details,
        realized_savings_inr=action.realized_savings_inr,
    )


@router.get("", response_model=list[ActionOut])
def list_actions(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_session)) -> list[ActionOut]:
    """List actions, newest first."""
    rows = db.exec(select(ActionLog).order_by(col(ActionLog.approved_at).desc(), col(ActionLog.id).desc()).limit(limit)).all()
    return [action_out(db, a) for a in rows]


MINI_SPAN = timedelta(minutes=30)


class MiniPoint(BaseModel):
    """Group load at one time, in servers' worth of work."""

    ts: datetime
    load: float


class ActionChart(BaseModel):
    """Load before and after an action, for the Activity mini-chart."""

    action_id: int
    changed_at: Optional[datetime]
    before_servers: Optional[int]
    after_servers: Optional[int]
    points: list[MiniPoint]


@router.get("/{action_id}/chart", response_model=ActionChart)
def action_chart(action_id: int, db: Session = Depends(get_session)) -> ActionChart:
    """Return the group's load from 30 minutes before the change to 30 minutes after (or now), 5-minute steps."""
    action = db.get(ActionLog, action_id)
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found.")
    rec = db.get(Recommendation, action.recommendation_id)
    at = as_utc(action.executed_at) or as_utc(action.approved_at)
    if rec is None or at is None:
        return ActionChart(action_id=action_id, changed_at=at, before_servers=None, after_servers=None, points=[])
    ids = [s.id for s in db.exec(select(Server).where(Server.group_id == rec.group_id)).all() if s.id is not None]
    end = min(at + MINI_SPAN, utcnow())
    m = metrics_frame(db, ids, at - MINI_SPAN)
    m = m[m["ts"] <= end] if len(m) else m
    demand = group_demand(m, freq="5min")
    points = [MiniPoint(ts=r["ts"].to_pydatetime(), load=round(float(r["demand"]), 3)) for _, r in demand.iterrows()]
    return ActionChart(action_id=action_id, changed_at=at, before_servers=rec.from_count,
                       after_servers=rec.to_count, points=points)
