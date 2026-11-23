"""Servers list, per-server detail (chart, what OptiServe sees, safety checks) and price overrides."""

from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.api.groups import FleetServer, fleet
from app.api.recommendations import RecommendationOut, rec_out
from app.auth import require_admin
from app.config import Settings, get_settings
from app.db import get_session
from app.engine.common import params_for, risk_params
from app.engine.explainer import what_we_see
from app.engine.forecaster import group_demand
from app.engine.pipeline import evaluate_group
from app.engine.pricing import PRICES_USD_HOUR
from app.jobs.engine_run import load_inputs
from app.models import Group, Recommendation, Server, utcnow

router = APIRouter(prefix="/api/servers", tags=["servers"], dependencies=[Depends(require_admin)])

CHART_PAST = timedelta(minutes=60)
CURRENT_STATUSES = ("pending", "blocked", "approved", "executing")


class ServerRow(FleetServer):
    """A server in the list, with its group and where its price comes from."""

    group_id: Optional[int]
    group_name: str
    managed: bool
    hourly_usd: Optional[float]  # the price in use
    price_source: Optional[str]  # override | table | None (unknown)
    table_hourly_usd: Optional[float]  # the default from the price table, for Settings


class PriceUpdate(BaseModel):
    """A price override in USD/hour; null goes back to the price table."""

    hourly_usd: Optional[float] = Field(default=None, ge=0, le=1000)


class ChartPoint(BaseModel):
    """One minute on the detail chart, in servers' worth of work (1.0 = one server fully busy)."""

    ts: datetime
    load: Optional[float] = None  # the group, measured
    server: Optional[float] = None  # this server, measured
    expected: Optional[float] = None  # forecast
    low: Optional[float] = None
    high: Optional[float] = None


class SafetyCheck(BaseModel):
    """One guardrail's verdict in plain words."""

    number: int
    rule: str
    status: str  # pass | adjusted | blocked
    message: str


class ServerDetail(BaseModel):
    """Everything the detail page shows."""

    server: ServerRow
    capacity: int  # servers running in the group (the capacity line)
    target_util_pct: int
    chart: list[ChartPoint]
    sees: list[str]
    safety: list[SafetyCheck]
    recommendation: Optional[RecommendationOut]
    as_of: datetime


def server_rows(db: Session, settings: Settings) -> list[ServerRow]:
    """Flatten the live fleet into list rows with price details."""
    servers = {s.id: s for s in db.exec(select(Server)).all()}
    rows: list[ServerRow] = []
    for g in fleet(db, settings):
        for tile in g.servers:
            s = servers[tile.id]
            table = PRICES_USD_HOUR.get((s.instance_type or "").strip().lower())
            override = s.hourly_cost_usd
            used = override if override is not None else table
            rows.append(ServerRow(
                **tile.model_dump(), group_id=g.id or None, group_name=g.name, managed=g.managed,
                hourly_usd=used, price_source="override" if override is not None else ("table" if table is not None else None),
                table_hourly_usd=table,
            ))
    return rows


def _row(db: Session, settings: Settings, server_id: int) -> ServerRow:
    """Return one list row or 404."""
    for r in server_rows(db, settings):
        if r.id == server_id:
            return r
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Server not found.")


def _num(v: object) -> Optional[float]:
    """Round a finite number, else None."""
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return round(f, 3) if np.isfinite(f) else None


@router.get("", response_model=list[ServerRow])
def list_servers(db: Session = Depends(get_session), settings: Settings = Depends(get_settings)) -> list[ServerRow]:
    """List every server with live busy %, status, cost and group."""
    return server_rows(db, settings)


@router.put("/{server_id}/price", response_model=ServerRow)
def set_price(
    server_id: int,
    body: PriceUpdate,
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ServerRow:
    """Override a server's hourly price (USD), or clear the override."""
    server = db.get(Server, server_id)
    if server is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Server not found.")
    server.hourly_cost_usd = body.hourly_usd
    db.add(server)
    db.commit()
    return _row(db, settings, server_id)


@router.get("/{server_id}", response_model=ServerDetail)
def server_detail(
    server_id: int, db: Session = Depends(get_session), settings: Settings = Depends(get_settings)
) -> ServerDetail:
    """Return the last 60 minutes and next 60 minutes, what OptiServe sees and the safety checks."""
    row = _row(db, settings, server_id)
    now = utcnow()
    params = params_for(settings.live_mode)
    target_util, _ = risk_params(settings.risk)
    server = db.get(Server, server_id)
    group = db.get(Group, server.group_id) if server and server.group_id else None
    rec_row = None
    chart: list[ChartPoint] = []
    safety: list[SafetyCheck] = []
    capacity = 0
    if group is None or server is None:
        sees = [row.reason, "This server is not in a group yet, so there is no forecast for it."]
        return ServerDetail(server=row, capacity=0, target_util_pct=round(target_util * 100), chart=[], sees=sees,
                            safety=[], recommendation=None, as_of=now)

    inputs = load_inputs(db, group, now, params)
    capacity = inputs.info.current
    if inputs.metrics.empty:
        sees = ["OptiServe has no numbers for this group yet. They appear within a minute of the first report."]
    else:
        d = evaluate_group(inputs.info, inputs.servers, inputs.metrics, now, params, settings.risk,
                           inputs.last_action_at, settings.usd_inr)
        recent = inputs.metrics[inputs.metrics["ts"] > pd.Timestamp(now - CHART_PAST)]
        demand = group_demand(recent)
        mine = recent[recent["server_id"] == server_id].copy()
        mine_series = (
            mine.assign(bucket=mine["ts"].dt.floor("1min")).groupby("bucket")["cpu_pct"].mean() / 100.0
            if len(mine) else pd.Series(dtype=float)
        )
        by_ts: dict[pd.Timestamp, ChartPoint] = {}
        for _, r in demand.iterrows():
            by_ts[r["ts"]] = ChartPoint(ts=r["ts"].to_pydatetime(), load=_num(r["demand"]))
        for ts, v in mine_series.items():
            p = by_ts.setdefault(ts, ChartPoint(ts=ts.to_pydatetime()))
            p.server = _num(v)
        if d.forecast.ok:
            for _, r in d.forecast.points.iterrows():
                p = by_ts.setdefault(r["ts"], ChartPoint(ts=r["ts"].to_pydatetime()))
                p.expected, p.low, p.high = _num(r["expected"]), _num(r["low"]), _num(r["high"])
        chart = [by_ts[k] for k in sorted(by_ts)]
        span = now - inputs.metrics["ts"].min().to_pydatetime()
        sees = what_we_see(
            status_reason=row.reason, mem_pct=row.mem_pct, provider=row.provider, group_name=group.name,
            capacity=capacity, forecast=d.forecast, now=pd.Timestamp(now), target_util=target_util,
            params=params, data_span=span, demand_now=float(demand["demand"].iloc[-1]) if len(demand) else None,
        )
        safety = [SafetyCheck(number=g.number, rule=g.rule, status=g.status, message=g.message) for g in d.guardrails]
    rec = db.exec(
        select(Recommendation).where(Recommendation.group_id == group.id, col(Recommendation.status).in_(CURRENT_STATUSES))
        .order_by(col(Recommendation.created_at).desc())
    ).first()
    rec_row = rec_out(db, rec) if rec else None
    return ServerDetail(server=row, capacity=capacity, target_util_pct=round(target_util * 100), chart=chart,
                        sees=sees, safety=safety, recommendation=rec_row, as_of=now)
