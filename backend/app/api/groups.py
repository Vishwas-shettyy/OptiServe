"""Live fleet for Home: every group with its servers, their status, load and cost."""

import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.auth import require_admin
from app.config import Settings, get_settings
from app.db import get_session
from app.engine.common import EngineParams, duration_words, params_for
from app.engine.pricing import hourly_usd, monthly_inr
from app.engine.profiler import is_idle, profile_servers
from app.jobs.engine_run import metrics_frame
from app.models import Group, MetricPoint, Server, as_utc, utcnow

router = APIRouter(prefix="/api/groups", tags=["groups"], dependencies=[Depends(require_admin)])

# Long idle windows (7 days in normal mode) are expensive to scan, so that one answer is cached briefly.
IDLE_CACHE_TTL_S = 60.0
_idle_cache: dict[str, tuple[float, set[int]]] = {}
_idle_lock = threading.Lock()


class FleetServer(BaseModel):
    """One live-fleet tile."""

    id: int
    name: str
    provider: str
    instance_type: Optional[str]
    state: str  # running | stopped | unknown
    status: str  # busy | normal | idle | unhealthy | stopped
    cpu_pct: Optional[float]
    mem_pct: Optional[float]
    monthly_cost_inr: Optional[float]  # None when the price is not known
    reason: str
    last_seen_at: Optional[datetime]


class FleetGroup(BaseModel):
    """A group of servers that scale together."""

    id: int
    name: str
    provider: str
    managed: bool
    min_size: int
    max_size: int
    desired: int
    servers: list[FleetServer]


def clear_idle_cache() -> None:
    """Forget cached idle answers (used by tests and after big changes)."""
    with _idle_lock:
        _idle_cache.clear()


def _finite(value: float) -> Optional[float]:
    """Return a rounded float, or None for NaN."""
    return round(float(value), 1) if value is not None and np.isfinite(value) else None


def idle_ids(db: Session, server_ids: list[int], now: datetime, params: EngineParams) -> set[int]:
    """Return the servers that have been idle for the whole idle window (cached for a minute)."""
    key = f"{params.idle_window}:{','.join(map(str, sorted(server_ids)))}"
    with _idle_lock:
        hit = _idle_cache.get(key)
        if hit and time.monotonic() - hit[0] < IDLE_CACHE_TTL_S:
            return hit[1]
    metrics = metrics_frame(db, server_ids, now - params.idle_window - timedelta(minutes=5))
    ts_now = pd.Timestamp(now)
    found = {sid for sid in server_ids if is_idle(metrics[metrics["server_id"] == sid], ts_now, params)}
    with _idle_lock:
        _idle_cache[key] = (time.monotonic(), found)
    return found


def last_points(db: Session, server_ids: list[int]) -> dict[int, datetime]:
    """Return each server's newest metric time (one aggregate query)."""
    if not server_ids:
        return {}
    rows = db.exec(
        select(MetricPoint.server_id, func.max(MetricPoint.ts))
        .where(col(MetricPoint.server_id).in_(server_ids))
        .group_by(MetricPoint.server_id)
    ).all()
    out: dict[int, datetime] = {}
    for sid, ts in rows:
        aware = as_utc(ts)
        if aware is not None:
            out[int(sid)] = aware
    return out


def fleet(db: Session, settings: Settings, now: Optional[datetime] = None) -> list[FleetGroup]:
    """Build the live fleet from real metrics: status by the engine's profiler, cost from the price table."""
    now = now or utcnow()
    params = params_for(settings.live_mode)
    groups = db.exec(select(Group).order_by(Group.name)).all()
    servers = db.exec(select(Server).order_by(Server.name)).all()
    running_ids = [s.id for s in servers if s.id is not None and s.state != "stopped"]
    short_idle = params.idle_window <= timedelta(hours=1)
    since = now - (params.idle_window if short_idle else max(params.recent_window, params.stale_after)) - timedelta(minutes=1)
    metrics = metrics_frame(db, running_ids, since)
    frame = pd.DataFrame([{"server_id": sid, "name": str(sid)} for sid in running_ids], columns=["server_id", "name"])
    profiles = profile_servers(metrics, frame, pd.Timestamp(now), params).set_index("server_id") if running_ids else None
    newest = last_points(db, running_ids)
    long_idle = set() if short_idle or not running_ids else idle_ids(db, running_ids, now, params)

    by_group: dict[Optional[int], list[FleetServer]] = {}
    for s in servers:
        assert s.id is not None
        price = hourly_usd(s.instance_type, s.hourly_cost_usd)
        cost = monthly_inr(price, settings.usd_inr) if price is not None and s.state == "running" else None
        if s.state == "stopped" or profiles is None or s.id not in profiles.index:
            tile = FleetServer(
                id=s.id, name=s.name, provider=s.provider, instance_type=s.instance_type, state=s.state,
                status="stopped", cpu_pct=None, mem_pct=None, monthly_cost_inr=None,
                reason="This server is stopped.", last_seen_at=as_utc(s.last_seen_at),
            )
        else:
            p = profiles.loc[s.id]
            status = str(p["status"])
            reason = str(p["reason"])
            last = newest.get(s.id)
            if status == "unhealthy" and last is not None and now - last > params.stale_after:
                reason = f"This server has sent no data for {duration_words(now - last)}."
            if status != "unhealthy" and s.id in long_idle:
                status, reason = "idle", f"Almost no work for {params.idle_window.days} days."
            tile = FleetServer(
                id=s.id, name=s.name, provider=s.provider, instance_type=s.instance_type, state=s.state,
                status=status, cpu_pct=_finite(p["avg_cpu"]), mem_pct=_finite(p["mem_pct"]),
                monthly_cost_inr=cost, reason=reason, last_seen_at=as_utc(s.last_seen_at),
            )
        by_group.setdefault(s.group_id, []).append(tile)

    out: list[FleetGroup] = []
    for g in groups:
        assert g.id is not None
        tiles = by_group.get(g.id, [])
        if tiles:
            out.append(FleetGroup(id=g.id, name=g.name, provider=g.provider, managed=g.managed,
                                  min_size=g.min_size, max_size=g.max_size, desired=g.desired, servers=tiles))
    orphans = by_group.get(None, [])
    if orphans:
        out.append(FleetGroup(id=0, name="Ungrouped", provider="agent", managed=False,
                              min_size=0, max_size=len(orphans), desired=len(orphans), servers=orphans))
    return out


@router.get("", response_model=list[FleetGroup])
def list_groups(db: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> list[FleetGroup]:
    """Return every group that has servers, with live tiles for each server."""
    return fleet(db, settings)
