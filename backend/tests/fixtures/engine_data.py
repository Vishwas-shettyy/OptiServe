"""Generated MetricPoint-shaped DataFrames for engine tests only. Never used outside tests."""

from typing import Callable, Optional, Union

import numpy as np
import pandas as pd

from app.engine.planner import GroupInfo

NOW = pd.Timestamp("2026-11-23 12:00", tz="UTC")
Shape = Union[float, Callable[[np.ndarray], np.ndarray]]


def _values(shape: Shape, minutes_ago: np.ndarray) -> np.ndarray:
    """Evaluate a constant or a function of minutes-before-NOW."""
    return shape(minutes_ago) if callable(shape) else np.full(len(minutes_ago), float(shape))


def server_metrics(
    server_id: int,
    span: pd.Timedelta,
    cpu: Shape,
    mem: Optional[Shape] = 30.0,
    net: Shape = 500.0,
    end: pd.Timestamp = NOW,
    freq: str = "1min",
    noise: float = 0.3,
    seed: int = 0,
) -> pd.DataFrame:
    """Return rows for one server from NOW − span to `end` (inclusive)."""
    ts = pd.date_range(NOW - span, end, freq=freq)
    ago = ((NOW - ts) / pd.Timedelta(minutes=1)).to_numpy(dtype=float)
    rng = np.random.default_rng(seed + server_id)
    cpu_v = np.clip(_values(cpu, ago) + rng.normal(0, noise, len(ts)), 0, 100)
    mem_v = np.clip(_values(mem, ago) + rng.normal(0, noise, len(ts)), 0, 100) if mem is not None else np.full(len(ts), np.nan)
    net_v = np.clip(_values(net, ago) + rng.normal(0, noise, len(ts)), 0, None)
    return pd.DataFrame({
        "server_id": server_id, "ts": ts, "cpu_pct": cpu_v, "mem_pct": mem_v,
        "net_in_kbps": net_v / 2, "net_out_kbps": net_v / 2, "disk_pct": 40.0, "requests_per_min": np.nan,
    })


def servers_frame(ids: list[int], group_id: int = 1, instance_type: str = "t3.medium", **extra: list) -> pd.DataFrame:
    """Return Server rows for a group."""
    df = pd.DataFrame({
        "server_id": ids, "name": [f"web-{i}" for i in ids], "group_id": group_id,
        "instance_type": instance_type, "hourly_cost_usd": None, "state": "running",
    })
    for key, values in extra.items():
        df[key] = values
    return df


def group(current: int, *, min_size: int = 1, max_size: int = 10, managed: bool = True, provider: str = "aws") -> GroupInfo:
    """Return a GroupInfo for group 1."""
    return GroupInfo(1, "web", provider, min_size, max_size, current, managed)


def rising_load() -> pd.DataFrame:
    """Three servers flat at 40% CPU for a day, then climbing to 62% over the last hour."""
    ramp = lambda ago: np.where(ago > 60, 40.0, 40.0 + 22.0 * (60 - ago) / 60)  # noqa: E731
    return pd.concat([server_metrics(i, pd.Timedelta(hours=26), ramp) for i in (1, 2, 3)], ignore_index=True)


def idle_server() -> pd.DataFrame:
    """Two busy-ish servers and one (id 3) doing nothing for 8 days."""
    span = pd.Timedelta(days=8)
    return pd.concat([
        server_metrics(1, span, 40.0), server_metrics(2, span, 40.0),
        server_metrics(3, span, 1.0, mem=10.0, net=10.0),
    ], ignore_index=True)


def quiet_group(n: int, cpu: float = 10.0, span: pd.Timedelta = pd.Timedelta(hours=26), mem: Optional[float] = 20.0) -> pd.DataFrame:
    """N servers with low steady load."""
    return pd.concat([server_metrics(i, span, cpu, mem=mem) for i in range(1, n + 1)], ignore_index=True)
