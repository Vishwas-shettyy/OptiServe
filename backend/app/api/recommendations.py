"""Copilot feed: list recommendations, approve (records who) and reject ("Not now")."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.actions import executor
from app.api.actions import ActionOut, action_out
from app.auth import require_admin
from app.config import Settings, get_settings
from app.db import get_session
from app.engine.common import params_for
from app.jobs.engine_run import OPEN_STATUSES, snooze_for
from app.models import Group, Recommendation, Server, utcnow

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"], dependencies=[Depends(require_admin)])

ALL_STATUSES = {"pending", "approved", "rejected", "blocked", "executing", "done", "failed", "expired"}
DEFAULT_STATUSES = "pending,blocked,approved,executing"


class RecommendationOut(BaseModel):
    """A recommendation card, with whether OptiServe may act on it."""

    id: int
    group_id: int
    group_name: str
    server_id: Optional[int]
    server_name: Optional[str]
    kind: str
    from_count: int
    to_count: int
    reason: str
    savings_month_inr: float
    confidence: float
    status: str
    blocked_reason: Optional[str]
    created_at: datetime
    expires_at: Optional[datetime]
    can_execute: bool
    recommendation_only_reason: Optional[str]


class ApproveResponse(BaseModel):
    """The recommendation after approval and its action log entry."""

    recommendation: RecommendationOut
    action: ActionOut


def rec_out(db: Session, rec: Recommendation) -> RecommendationOut:
    """Convert a recommendation row to its card."""
    assert rec.id is not None
    group = db.get(Group, rec.group_id)
    server = db.get(Server, rec.server_id) if rec.server_id else None
    only = executor.refusal(db, rec) if rec.kind != "hold" else None
    return RecommendationOut(
        id=rec.id, group_id=rec.group_id, group_name=group.name if group else "", server_id=rec.server_id,
        server_name=server.name if server else None, kind=rec.kind, from_count=rec.from_count, to_count=rec.to_count,
        reason=rec.reason, savings_month_inr=rec.savings_month_inr, confidence=rec.confidence, status=rec.status,
        blocked_reason=rec.blocked_reason, created_at=rec.created_at, expires_at=rec.expires_at,
        can_execute=rec.kind != "hold" and only is None, recommendation_only_reason=only,
    )


def _get(db: Session, rec_id: int) -> Recommendation:
    """Return the recommendation or 404."""
    rec = db.get(Recommendation, rec_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Suggestion not found.")
    return rec


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(
    status_filter: str = Query(DEFAULT_STATUSES, alias="status", description="Comma-separated statuses, or 'all'."),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_session),
) -> list[RecommendationOut]:
    """List recommendations, newest first (open and in-progress ones by default)."""
    wanted = ALL_STATUSES if status_filter == "all" else {s.strip() for s in status_filter.split(",") if s.strip()}
    if not wanted <= ALL_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown status: {', '.join(sorted(wanted - ALL_STATUSES))}.")
    rows = db.exec(
        select(Recommendation).where(col(Recommendation.status).in_(wanted))
        .order_by(col(Recommendation.created_at).desc(), col(Recommendation.id).desc()).limit(limit)
    ).all()
    return [rec_out(db, r) for r in rows]


@router.post("/{rec_id}/approve", response_model=ApproveResponse)
def approve_recommendation(
    rec_id: int,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    admin: str = Depends(require_admin),
) -> ApproveResponse:
    """Approve a suggestion: guardrails run again, then the change runs (or is dry-run) and is logged."""
    rec = _get(db, rec_id)
    try:
        action = executor.approve(db, rec, admin, settings)
    except executor.Refused as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.refresh(rec)
    return ApproveResponse(recommendation=rec_out(db, rec), action=action_out(db, action))


@router.post("/{rec_id}/reject", response_model=RecommendationOut)
def reject_recommendation(
    rec_id: int, db: Session = Depends(get_session), settings: Settings = Depends(get_settings),
) -> RecommendationOut:
    """'Not now': hide this suggestion; the same change is not suggested again for a while."""
    rec = _get(db, rec_id)
    if rec.status not in OPEN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This suggestion is {rec.status}, so it cannot be dismissed.")
    rec.status = "rejected"
    rec.expires_at = utcnow() + snooze_for(params_for(settings.live_mode))
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec_out(db, rec)
