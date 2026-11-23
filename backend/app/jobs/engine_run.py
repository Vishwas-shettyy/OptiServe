"""Database side of the engine: load a group's inputs, upsert recommendations, store forecasts, score accuracy."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from sqlmodel import Session, col, select

from app.config import Settings
from app.engine.accuracy import score_forecasts
from app.engine.common import EngineParams, params_for, risk_params
from app.engine.forecaster import ForecastResult, group_demand, plan_forecast
from app.engine.pipeline import Decision, evaluate_group
from app.engine.planner import GroupInfo
from app.models import ActionLog, Forecast, Group, MetricPoint, Recommendation, Server, as_utc, utcnow

log = logging.getLogger(__name__)

OPEN_STATUSES = ("pending", "blocked")
IN_FLIGHT_STATUSES = ("approved", "executing")
EXPIRE_AFTER = timedelta(minutes=15)
METRIC_FIELDS = ("server_id", "ts", "cpu_pct", "mem_pct", "net_in_kbps", "net_out_kbps", "disk_pct", "requests_per_min")
SERVER_FIELDS = ("server_id", "name", "group_id", "instance_type", "hourly_cost_usd", "state")


def snooze_for(params: EngineParams) -> timedelta:
    """Return how long a rejected ('Not now') suggestion stays hidden."""
    return timedelta(minutes=10) if params.live_mode else timedelta(hours=1)


def load_window(params: EngineParams) -> timedelta:
    """Return how much metric history the engine needs (idle window or minimum data, plus an hour)."""
    return max(params.idle_window, params.min_data, params.short_history) + timedelta(hours=1)


@dataclass
class GroupInputs:
    """Everything evaluate_group needs for one group, read from the database."""

    info: GroupInfo
    servers: pd.DataFrame
    metrics: pd.DataFrame
    last_action_at: Optional[datetime]


def servers_frame(db: Session, group_id: int) -> pd.DataFrame:
    """Return the group's servers as a DataFrame in the engine's shape."""
    rows = db.exec(select(Server).where(Server.group_id == group_id).order_by(Server.id)).all()
    return pd.DataFrame(
        [{"server_id": s.id, "name": s.name, "group_id": s.group_id, "instance_type": s.instance_type,
          "hourly_cost_usd": s.hourly_cost_usd, "state": s.state} for s in rows],
        columns=list(SERVER_FIELDS),
    )


def metrics_frame(db: Session, server_ids: list[int], since: datetime) -> pd.DataFrame:
    """Return MetricPoint rows for the servers since a time."""
    if not server_ids:
        return pd.DataFrame(columns=list(METRIC_FIELDS))
    stmt = select(*(getattr(MetricPoint, f) for f in METRIC_FIELDS)).where(
        col(MetricPoint.server_id).in_(server_ids), MetricPoint.ts >= since
    )
    df = pd.DataFrame(db.exec(stmt).all(), columns=list(METRIC_FIELDS))
    if len(df):
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def last_action_at(db: Session, group_id: int) -> Optional[datetime]:
    """Return when the last real (not dry-run) change on this group was made."""
    stmt = (
        select(ActionLog.executed_at)
        .join(Recommendation, col(Recommendation.id) == ActionLog.recommendation_id)
        .where(Recommendation.group_id == group_id, col(ActionLog.executed_at).is_not(None))
        .where((col(ActionLog.result).is_(None)) | (ActionLog.result != "dry_run"))
        .order_by(col(ActionLog.executed_at).desc())
    )
    return as_utc(db.exec(stmt).first())


def group_info(group: Group, servers: pd.DataFrame) -> GroupInfo:
    """Return the engine's view of a group; an ASG's size is its desired capacity."""
    assert group.id is not None
    running = int((servers["state"] != "stopped").sum()) if len(servers) else 0
    current = int(group.desired) if group.asg_name else running
    return GroupInfo(group.id, group.name, group.provider, group.min_size, group.max_size, current, group.managed)


def load_inputs(db: Session, group: Group, now: datetime, params: EngineParams) -> GroupInputs:
    """Read a group's servers, metrics and last action from the database."""
    assert group.id is not None
    servers = servers_frame(db, group.id)
    metrics = metrics_frame(db, [int(i) for i in servers["server_id"]], now - load_window(params))
    return GroupInputs(group_info(group, servers), servers, metrics, last_action_at(db, group.id))


def points_json(forecast: ForecastResult) -> str:
    """Serialise forecast points as [{ts, expected, low, high}]."""
    pts = forecast.points
    return json.dumps([
        {"ts": ts.isoformat(), "expected": round(float(e), 4), "low": round(float(lo), 4), "high": round(float(hi), 4)}
        for ts, e, lo, hi in zip(pts["ts"], pts["expected"], pts["low"], pts["high"])
    ])


def _same(rec: Recommendation, d: Decision) -> bool:
    """True when a stored recommendation proposes the same change as a fresh decision."""
    return (rec.kind, rec.to_count, rec.server_id) == (d.kind, d.to_count, d.server_id)


def expire_stale(db: Session, now: datetime) -> int:
    """Mark open recommendations past their expiry as expired; return how many."""
    stale = db.exec(
        select(Recommendation).where(col(Recommendation.status).in_(OPEN_STATUSES), Recommendation.expires_at < now)
    ).all()
    for rec in stale:
        rec.status = "expired"
        db.add(rec)
    return len(stale)


def upsert_recommendation(
    db: Session, group_id: int, d: Decision, now: datetime, params: EngineParams,
) -> Optional[Recommendation]:
    """Keep one open recommendation per group: refresh it if unchanged, else expire it and add the new one."""
    if db.exec(
        select(Recommendation.id).where(
            Recommendation.group_id == group_id, col(Recommendation.status).in_(IN_FLIGHT_STATUSES)
        )
    ).first():
        return None  # an approved change is running; wait for it to finish
    open_recs = db.exec(
        select(Recommendation)
        .where(Recommendation.group_id == group_id, col(Recommendation.status).in_(OPEN_STATUSES))
        .order_by(col(Recommendation.created_at).desc())
    ).all()
    snoozed = db.exec(
        select(Recommendation).where(
            Recommendation.group_id == group_id, Recommendation.status == "rejected", Recommendation.expires_at > now
        )
    ).all()
    keep: Optional[Recommendation] = next((r for r in open_recs if _same(r, d)), None)
    for rec in open_recs:
        if rec is not keep:
            rec.status = "expired"
            db.add(rec)
    if keep is None and any(_same(r, d) for r in snoozed):
        return None  # the admin said "Not now" to this exact change recently
    rec = keep or Recommendation(group_id=group_id, kind=d.kind, from_count=d.from_count, to_count=d.to_count,
                                 server_id=d.server_id, reason=d.reason, created_at=now)
    rec.from_count = d.from_count
    rec.reason = d.reason
    rec.savings_month_inr = round(float(d.savings_month_inr), 2)
    rec.confidence = float(d.confidence)
    rec.status = d.status
    rec.blocked_reason = d.blocked_reason
    rec.expires_at = now + EXPIRE_AFTER
    db.add(rec)
    return rec


def run_engine(db: Session, settings: Settings, now: Optional[datetime] = None) -> list[Recommendation]:
    """Evaluate every group, store its short forecast and upsert its recommendation."""
    now = now or utcnow()
    params = params_for(settings.live_mode)
    expire_stale(db, now)
    out: list[Recommendation] = []
    for group in db.exec(select(Group).order_by(Group.id)).all():
        assert group.id is not None
        inputs = load_inputs(db, group, now, params)
        if inputs.metrics.empty:
            continue  # nothing reported yet: the UI shows the empty state, not a guess
        d = evaluate_group(inputs.info, inputs.servers, inputs.metrics, now, params,
                           settings.risk, inputs.last_action_at, settings.usd_inr)
        if d.forecast.ok:
            db.add(Forecast(group_id=group.id, created_at=now, horizon="short",
                            points_json=points_json(d.forecast), method=d.forecast.method))
        rec = upsert_recommendation(db, group.id, d, now, params)
        if rec is not None:
            out.append(rec)
    db.commit()
    for rec in out:
        db.refresh(rec)
    return out


def run_plan_forecast(db: Session, settings: Settings, now: Optional[datetime] = None) -> dict[int, str]:
    """Store a 7-day hourly forecast for every group with enough history; return group id → status message."""
    now = now or utcnow()
    params = params_for(settings.live_mode)
    _, z = risk_params(settings.risk)
    out: dict[int, str] = {}
    for group in db.exec(select(Group).order_by(Group.id)).all():
        assert group.id is not None
        servers = servers_frame(db, group.id)
        metrics = metrics_frame(db, [int(i) for i in servers["server_id"]], now - timedelta(days=21))
        hourly = group_demand(metrics, freq="1h")
        fc = plan_forecast(hourly, now, params, z)
        out[group.id] = fc.message
        if fc.ok:
            db.add(Forecast(group_id=group.id, created_at=now, horizon="plan", points_json=points_json(fc), method=fc.method))
    db.commit()
    return out


def compute_accuracy(db: Session, now: Optional[datetime] = None, window: timedelta = timedelta(hours=24)) -> dict:
    """Return {accuracy_pct, wape, points} of the last 24 h of short forecasts against actual demand."""
    now = now or utcnow()
    since = now - window
    total_points, weighted = 0, 0.0
    for group in db.exec(select(Group)).all():
        assert group.id is not None
        rows = db.exec(
            select(Forecast.points_json).where(
                Forecast.group_id == group.id, Forecast.horizon == "short", Forecast.created_at >= since - timedelta(hours=1)
            )
        ).all()
        pts = [p for raw in rows for p in json.loads(raw)]
        if not pts:
            continue
        servers = servers_frame(db, group.id)
        actual = group_demand(metrics_frame(db, [int(i) for i in servers["server_id"]], since))
        score = score_forecasts(pd.DataFrame(pts), actual, pd.Timestamp(now), window)
        if score["wape"] is not None and score["points"]:
            total_points += score["points"]
            weighted += score["wape"] * score["points"]
    if not total_points:
        return {"accuracy_pct": None, "wape": None, "points": 0}
    w = weighted / total_points
    return {"accuracy_pct": round(max(0.0, min(100.0, 100.0 - w * 100.0)), 1), "wape": round(w, 4), "points": total_points}


def downsample(db: Session, now: Optional[datetime] = None, keep: timedelta = timedelta(days=14)) -> int:
    """Average raw MetricPoint rows older than 14 days into 5-minute buckets; return rows removed."""
    now = now or utcnow()
    cutoff = now - keep
    old = db.exec(select(MetricPoint).where(MetricPoint.ts < cutoff)).all()
    if not old:
        return 0
    df = pd.DataFrame([{f: getattr(p, f) for f in METRIC_FIELDS} | {"id": p.id} for p in old])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["bucket"] = df["ts"].dt.floor("5min")
    counts = df.groupby(["server_id", "bucket"])["id"].transform("size")
    crowded = df[counts > 1]
    if crowded.empty:
        return 0
    by_id = {p.id: p for p in old}
    removed = 0
    for (server_id, bucket), grp in crowded.groupby(["server_id", "bucket"]):
        avg = grp[list(METRIC_FIELDS[2:])].mean(numeric_only=True)
        for pid in grp["id"]:
            db.delete(by_id[int(pid)])
            removed += 1

        def val(name: str) -> Optional[float]:
            """Return the bucket average or None when every sample was missing."""
            v = avg.get(name)
            return None if v is None or pd.isna(v) else float(v)

        db.add(MetricPoint(
            server_id=int(server_id), ts=bucket.to_pydatetime(), cpu_pct=val("cpu_pct") or 0.0, mem_pct=val("mem_pct"),
            net_in_kbps=val("net_in_kbps") or 0.0, net_out_kbps=val("net_out_kbps") or 0.0,
            disk_pct=val("disk_pct"), requests_per_min=val("requests_per_min"),
        ))
        removed -= 1
    db.commit()
    return removed
