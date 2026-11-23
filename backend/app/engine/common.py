"""Shared engine settings, risk helpers and DataFrame normalisation (CLAUDE.md §6–§7). Pure: no I/O."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Union

import pandas as pd

HOURS_PER_MONTH = 730.0
DEFAULT_RISK = 0.5
RISK_COST = {"target_util": 0.85, "z": 0.5}
RISK_SAFE = {"target_util": 0.55, "z": 2.0}
METRIC_COLUMNS = [
    "server_id", "ts", "cpu_pct", "mem_pct", "net_in_kbps", "net_out_kbps", "disk_pct", "requests_per_min",
]


@dataclass(frozen=True)
class EngineParams:
    """Thresholds and time windows used by every engine step."""

    live_mode: bool = False
    idle_window: timedelta = timedelta(days=7)
    cooldown: timedelta = timedelta(minutes=15)
    lead_time: timedelta = timedelta(minutes=30)
    min_data: timedelta = timedelta(hours=24)
    stale_after: timedelta = timedelta(minutes=3)
    recent_window: timedelta = timedelta(minutes=10)
    short_history: timedelta = timedelta(minutes=60)
    short_horizon_min: int = 60
    short_min_points: int = 10
    idle_cpu_p95: float = 5.0
    idle_net_kbps: float = 50.0
    busy_cpu: float = 75.0
    unhealthy_mem: float = 90.0
    max_step_down: int = 1
    low_confidence_ratio: float = 1.0
    plan_min_days: int = 7


def params_for(live_mode: bool) -> EngineParams:
    """Return normal windows, or the shorter live-mode windows used for live demos."""
    if live_mode:
        return EngineParams(
            live_mode=True,
            idle_window=timedelta(minutes=10),
            cooldown=timedelta(minutes=3),
            lead_time=timedelta(minutes=5),
            min_data=timedelta(minutes=15),
            recent_window=timedelta(minutes=3),
        )
    return EngineParams()


def risk_params(risk: float = DEFAULT_RISK) -> tuple[float, float]:
    """Return (target_util, z) interpolated from cost (risk=0) to safe (risk=1); default 0.5 → 0.70."""
    r = min(max(float(risk), 0.0), 1.0)
    target = RISK_COST["target_util"] + (RISK_SAFE["target_util"] - RISK_COST["target_util"]) * r
    z = RISK_COST["z"] + (RISK_SAFE["z"] - RISK_COST["z"]) * r
    return round(target, 4), round(z, 4)


def utc(value: Union[datetime, pd.Timestamp, str]) -> pd.Timestamp:
    """Return a tz-aware UTC Timestamp; naive values are taken to be UTC already."""
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def normalize_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    """Return a sorted copy of MetricPoint rows with UTC ts and every metric column present as float."""
    m = metrics.copy() if metrics is not None else pd.DataFrame(columns=METRIC_COLUMNS)
    for col in METRIC_COLUMNS:
        if col not in m.columns:
            m[col] = pd.Series(dtype=float) if col != "ts" else pd.Series(dtype="datetime64[ns, UTC]")
    m["ts"] = pd.to_datetime(m["ts"], utc=True)
    for col in METRIC_COLUMNS[2:]:
        m[col] = pd.to_numeric(m[col], errors="coerce").astype(float)
    return m.sort_values("ts").reset_index(drop=True)


def duration_words(span: timedelta) -> str:
    """Return a plain duration such as '12 minutes', '5 hours' or '3 days'."""
    minutes = max(0, int(span.total_seconds() // 60))
    if minutes < 120:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hours"
    return f"{hours // 24} days"
