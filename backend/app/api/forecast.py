"""Capacity weather for Home: the next 24 h (60 min in live mode) as sun / cloud / storm slots."""

import json
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.auth import require_admin
from app.config import Settings, get_settings
from app.db import get_session
from app.engine.weather import weather_slots
from app.models import Forecast, Group, MetricPoint, Server, as_utc, utcnow

router = APIRouter(prefix="/api/forecast", tags=["forecast"], dependencies=[Depends(require_admin)])

SHORT_HORIZON = timedelta(minutes=60)
PLAN_HORIZON = timedelta(hours=24)
SHORT_FRESH = timedelta(minutes=10)  # short forecasts are stored every minute
PLAN_FRESH = timedelta(hours=3)  # plan forecasts are stored every hour
PLAN_MIN_DAYS = 7


class WeatherSlotOut(BaseModel):
    """One weather icon: when it starts and how full the current servers are expected to be."""

    start: datetime
    kind: str  # sun | cloud | storm
    expected_util: float
    high_util: float


class WeatherOut(BaseModel):
    """The weather strip. Empty slots with a plain message mean OptiServe has nothing honest to show yet."""

    horizon: str  # "60 min" | "24 h"
    live_mode: bool
    status: str  # ok | learning | no_data
    message: str
    capacity: int
    slots: list[WeatherSlotOut]
    as_of: datetime


def latest_points(db: Session, horizon: str, since: datetime) -> pd.DataFrame:
    """Sum the newest fresh forecast of each group into one fleet-wide series (server-equivalents)."""
    frames: list[pd.DataFrame] = []
    for group_id in db.exec(select(Group.id)).all():
        row = db.exec(
            select(Forecast)
            .where(Forecast.group_id == group_id, Forecast.horizon == horizon, Forecast.created_at >= since)
            .order_by(col(Forecast.created_at).desc())
        ).first()
        if row is not None:
            frames.append(pd.DataFrame(json.loads(row.points_json)))
    if not frames:
        return pd.DataFrame(columns=["ts", "expected", "low", "high"])
    df = pd.concat(frames)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.groupby("ts", as_index=False)[["expected", "low", "high"]].sum()


def collected_days(db: Session, now: datetime) -> float:
    """Return how many days of history the fleet has (for the 'learning' message)."""
    first = as_utc(db.exec(select(func.min(MetricPoint.ts))).one())
    return max(0.0, (now - first).total_seconds() / 86_400) if first else 0.0


def weather(db: Session, settings: Settings, now: Optional[datetime] = None) -> WeatherOut:
    """Build the strip from stored forecasts: plan (24 h) when available, else short (60 min)."""
    now = now or utcnow()
    running = db.exec(select(Server).where(Server.state == "running")).all()
    capacity = len(running)
    message = ""
    status = "ok"
    horizon, span = "60 min", SHORT_HORIZON
    points = pd.DataFrame()
    if not settings.live_mode:
        points = latest_points(db, "plan", now - PLAN_FRESH)
        if not points.empty:
            horizon, span = "24 h", PLAN_HORIZON
        else:
            days = min(collected_days(db, now), float(PLAN_MIN_DAYS))
            status = "learning"
            message = (
                f"OptiServe is learning: {days:.0f} of {PLAN_MIN_DAYS} days collected for the 24-hour view. "
                "Showing the next 60 minutes meanwhile."
            )
    if points.empty:
        points = latest_points(db, "short", now - SHORT_FRESH)
    slots = weather_slots(points, float(capacity), now, span) if capacity else []
    if not slots:
        status = "no_data"
        message = message or "OptiServe needs about 15 minutes of numbers before it can forecast."
        if capacity == 0:
            message = "No servers are running, so there is nothing to forecast."
    return WeatherOut(
        horizon=horizon,
        live_mode=settings.live_mode,
        status=status,
        message=message,
        capacity=capacity,
        slots=[WeatherSlotOut(start=as_utc(s.start) or s.start, kind=s.kind, expected_util=s.expected_util,
                              high_util=s.high_util) for s in slots],
        as_of=now,
    )


@router.get("/weather", response_model=WeatherOut)
def get_weather(db: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> WeatherOut:
    """Return the capacity weather strip."""
    return weather(db, settings)
