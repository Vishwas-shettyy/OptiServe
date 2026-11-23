"""Headline numbers for Home: how busy, how many servers, what they cost, what can be and was saved, accuracy."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.actions.executor import monthly_cost_inr
from app.auth import require_admin
from app.config import Settings, get_settings
from app.db import get_session
from app.engine.common import params_for
from app.engine.pricing import hourly_usd
from app.jobs import scheduler
from app.jobs.engine_run import compute_accuracy, metrics_frame
from app.models import ActionLog, Recommendation, Server, utcnow

router = APIRouter(prefix="/api/stats", tags=["stats"], dependencies=[Depends(require_admin)])


class StatsOut(BaseModel):
    """Home headline numbers. None means 'not known yet' (no data), never a guess."""

    avg_busy_pct: Optional[float]
    servers: int
    servers_without_price: int
    monthly_cost_inr: float
    potential_savings_inr: float
    realized_savings_inr: float
    accuracy_pct: Optional[float]
    accuracy_points: int
    live_mode: bool
    dry_run: bool
    as_of: datetime


@router.get("", response_model=StatsOut)
def get_stats(db: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> StatsOut:
    """Return the headline numbers from real data only."""
    now = utcnow()
    params = params_for(settings.live_mode)
    running = db.exec(select(Server).where(Server.state == "running")).all()
    ids = [s.id for s in running if s.id is not None]
    recent = metrics_frame(db, ids, now - params.recent_window)
    busy = None
    if len(recent):
        per_server = recent.groupby("server_id")["cpu_pct"].mean()
        busy = round(float(per_server.mean()), 1)
    potential = db.exec(
        select(func.coalesce(func.sum(Recommendation.savings_month_inr), 0.0)).where(
            col(Recommendation.status).in_(("pending", "approved", "executing")), Recommendation.savings_month_inr > 0
        )
    ).one()
    realized = db.exec(select(func.coalesce(func.sum(ActionLog.realized_savings_inr), 0.0))).one()
    acc = scheduler.ACCURACY if scheduler.ACCURACY["updated_at"] is not None else compute_accuracy(db, now)
    return StatsOut(
        avg_busy_pct=busy,
        servers=len(running),
        servers_without_price=sum(1 for s in running if hourly_usd(s.instance_type, s.hourly_cost_usd) is None),
        monthly_cost_inr=monthly_cost_inr(list(running), settings.usd_inr),
        potential_savings_inr=round(float(potential), 2),
        realized_savings_inr=round(float(realized), 2),
        accuracy_pct=acc["accuracy_pct"],
        accuracy_points=int(acc["points"]),
        live_mode=settings.live_mode,
        dry_run=settings.dry_run,
        as_of=now,
    )
