"""Server status (busy / normal / idle / unhealthy) and idle detection. Pure: no I/O."""

from typing import Optional

import numpy as np
import pandas as pd

from app.engine.common import EngineParams, duration_words, normalize_metrics, utc

PROFILE_COLUMNS = [
    "server_id", "name", "status", "avg_cpu", "p95_cpu", "mem_pct", "net_kbps",
    "idle", "healthy", "health_reason", "last_seen", "reason",
]


def health_check(
    server_metrics: pd.DataFrame, now: pd.Timestamp, params: EngineParams, status_check_ok: Optional[bool] = True,
) -> tuple[bool, str]:
    """Return (healthy, plain reason): failed status checks, memory over 90% or no data for 3 minutes."""
    if status_check_ok is False:
        return False, "failed its AWS health checks"
    if server_metrics.empty:
        return False, "has not sent any data yet"
    silent = now - server_metrics["ts"].max()
    if silent > params.stale_after:
        return False, f"has sent no data for {duration_words(silent)}"
    recent_mem = server_metrics.loc[server_metrics["ts"] > now - params.stale_after, "mem_pct"].dropna()
    if len(recent_mem) and float(recent_mem.mean()) > params.unhealthy_mem:
        return False, f"memory is {float(recent_mem.mean()):.0f}% full"
    return True, ""


def is_idle(server_metrics: pd.DataFrame, now: pd.Timestamp, params: EngineParams) -> bool:
    """Return True when p95 CPU < 5% and p95 network < 50 kbps across the whole idle window."""
    if server_metrics.empty:
        return False
    start = now - params.idle_window
    if server_metrics["ts"].min() > start + params.idle_window * 0.05:
        return False
    window = server_metrics[server_metrics["ts"] > start]
    if window.empty:
        return False
    net = window["net_in_kbps"].fillna(0.0) + window["net_out_kbps"].fillna(0.0)
    return bool(window["cpu_pct"].quantile(0.95) < params.idle_cpu_p95 and net.quantile(0.95) < params.idle_net_kbps)


def _reason(status: str, avg_cpu: float, mem: float, health_reason: str, params: EngineParams) -> str:
    """Return a short plain sentence for a server status."""
    if status == "unhealthy":
        return f"This server {health_reason}."
    if status == "idle":
        return f"Almost no work for {duration_words(params.idle_window)}."
    if status == "busy":
        return f"Working hard: {max(avg_cpu, mem if np.isfinite(mem) else 0.0):.0f}% busy."
    return f"Running normally at {avg_cpu:.0f}% busy."


def profile_servers(
    metrics: pd.DataFrame, servers: pd.DataFrame, now: pd.Timestamp, params: EngineParams,
) -> pd.DataFrame:
    """Return one status row per server. `servers` needs server_id and name; status_check_ok is optional."""
    now = utc(now)
    m = normalize_metrics(metrics)
    rows = []
    for srv in servers.to_dict("records"):
        sm = m[m["server_id"] == srv["server_id"]]
        recent = sm[sm["ts"] > now - params.recent_window]
        avg_cpu = float(recent["cpu_pct"].mean()) if len(recent) else float("nan")
        p95_cpu = float(recent["cpu_pct"].quantile(0.95)) if len(recent) else float("nan")
        mem = float(recent["mem_pct"].mean()) if recent["mem_pct"].notna().any() else float("nan")
        net = float((recent["net_in_kbps"].fillna(0) + recent["net_out_kbps"].fillna(0)).mean()) if len(recent) else float("nan")
        check = srv.get("status_check_ok", True)
        check = None if check is None or (isinstance(check, float) and np.isnan(check)) else bool(check)
        healthy, health_reason = health_check(sm, now, params, check)
        idle = healthy and is_idle(sm, now, params)
        if not healthy:
            status = "unhealthy"
        elif idle:
            status = "idle"
        elif avg_cpu >= params.busy_cpu or (np.isfinite(mem) and mem >= params.unhealthy_mem - 5):
            status = "busy"
        else:
            status = "normal"
        rows.append({
            "server_id": srv["server_id"], "name": srv.get("name", str(srv["server_id"])), "status": status,
            "avg_cpu": avg_cpu, "p95_cpu": p95_cpu, "mem_pct": mem, "net_kbps": net, "idle": idle,
            "healthy": healthy, "health_reason": health_reason,
            "last_seen": sm["ts"].max() if len(sm) else pd.NaT,
            "reason": _reason(status, avg_cpu, mem, health_reason, params),
        })
    return pd.DataFrame(rows, columns=PROFILE_COLUMNS)
