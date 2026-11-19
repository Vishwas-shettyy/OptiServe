"""Server status and waste profiling."""

import numpy as np
import pandas as pd

from engine import config

PROFILE_COLUMNS = [
    "server_id", "name", "service", "instance_type", "monthly_cost", "avg_cpu", "p95_cpu",
    "max_mem_24h", "err_24h", "idle_since", "status", "wasted_monthly", "reason",
]


def _idle_since(server_metrics: pd.DataFrame) -> pd.Timestamp:
    """Return the start of the trailing run of days with daily p95 CPU under the zombie threshold."""
    daily = server_metrics.set_index("timestamp")["cpu_pct"].resample("D").quantile(0.95)
    idle = (daily < config.ZOMBIE_CPU_P95).to_numpy()
    if len(idle) == 0 or not idle[-1]:
        return pd.NaT
    start = len(idle) - 1
    while start > 0 and idle[start - 1]:
        start -= 1
    return pd.Timestamp(daily.index[start])


def _classify(avg_cpu: float, p95_cpu: float, max_mem: float, err: float) -> str:
    """Return the status using the section 6 priority order."""
    if max_mem > config.UNHEALTHY_MEM or err > config.UNHEALTHY_ERROR:
        return "Risky"
    if p95_cpu < config.ZOMBIE_CPU_P95:
        return "Zombie"
    if p95_cpu > config.HOT_CPU_P95:
        return "Hot"
    if avg_cpu < config.WASTEFUL_AVG_CPU:
        return "Wasteful"
    return "Right-sized"


def _reason(status: str, avg_cpu: float, p95_cpu: float, max_mem: float, err: float, idle_days: int) -> str:
    """Return a short human sentence explaining the status."""
    if status == "Risky":
        parts = []
        if max_mem > config.UNHEALTHY_MEM:
            parts.append(f"memory hit {max_mem:.0f}%")
        if err > config.UNHEALTHY_ERROR:
            parts.append(f"error rate {err:.1%}")
        return ("In the last 24h " + " and ".join(parts) + " — likely failing").capitalize()
    if status == "Zombie":
        return f"CPU under {config.ZOMBIE_CPU_P95:.0f}% for {idle_days} days"
    if status == "Hot":
        return f"Peak CPU {p95_cpu:.0f}% — running close to its limit"
    if status == "Wasteful":
        return f"Average CPU only {avg_cpu:.0f}% — paying for idle capacity"
    return f"Average CPU {avg_cpu:.0f}%, peak {p95_cpu:.0f}% — well sized"


def profile_servers(metrics: pd.DataFrame, servers: pd.DataFrame) -> pd.DataFrame:
    """Return one status row per server."""
    end = metrics["timestamp"].max()
    window = metrics[metrics["timestamp"] > end - pd.Timedelta(days=config.ZOMBIE_DAYS)]
    health = metrics[metrics["timestamp"] > end - pd.Timedelta(hours=24)]
    rows = []
    for srv in servers.itertuples(index=False):
        w = window[window["server_id"] == srv.server_id]
        h = health[health["server_id"] == srv.server_id]
        avg_cpu = float(w["cpu_pct"].mean())
        p95_cpu = float(w["cpu_pct"].quantile(0.95))
        max_mem = float(h["mem_pct"].max())
        err = float(h["error_rate"].mean())
        status = _classify(avg_cpu, p95_cpu, max_mem, err)
        idle = _idle_since(metrics[metrics["server_id"] == srv.server_id]) if status == "Zombie" else pd.NaT
        idle_days = int(round((end - idle) / pd.Timedelta(days=1))) if pd.notna(idle) else 0
        if status == "Zombie":
            wasted = float(srv.monthly_cost)
        elif status == "Wasteful":
            wasted = float(srv.monthly_cost) * max(0.0, 1.0 - avg_cpu / config.TARGET_CPU_FOR_WASTE)
        else:
            wasted = 0.0
        rows.append((
            srv.server_id, srv.name, srv.service, srv.instance_type, float(srv.monthly_cost), avg_cpu, p95_cpu,
            max_mem, err, idle, status, wasted, _reason(status, avg_cpu, p95_cpu, max_mem, err, idle_days),
        ))
    profile = pd.DataFrame(rows, columns=PROFILE_COLUMNS)
    profile["idle_since"] = pd.to_datetime(profile["idle_since"])
    return profile


def waste_score(profile: pd.DataFrame) -> float:
    """Return wasted monthly cost as a percentage of total cost."""
    total = float(profile["monthly_cost"].sum())
    if total <= 0:
        return 0.0
    return float(np.round(profile["wasted_monthly"].sum() / total * 100.0, 4))
