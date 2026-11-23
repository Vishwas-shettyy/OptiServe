"""Servers needed from the forecast's high band and the risk setting, and the raw proposal. Pure."""

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from app.engine.forecaster import ForecastResult

REMOVAL_KINDS = ("scale_down", "stop_idle")


@dataclass(frozen=True)
class GroupInfo:
    """The group being planned: limits, current size and whether OptiServe may act on it."""

    group_id: int
    name: str
    provider: str
    min_size: int
    max_size: int
    current: int
    managed: bool


@dataclass(frozen=True)
class Proposal:
    """A change before or after guardrails: kind, from/to count and the server for stop_idle."""

    kind: str
    from_count: int
    to_count: int
    server_id: Optional[int] = None
    server_name: Optional[str] = None


def servers_needed(high: float, target_util: float) -> int:
    """Return ceil(high / target_util), at least 1."""
    return max(1, int(math.ceil(float(high) / float(target_util) - 1e-9)))


def needed_series(points: pd.DataFrame, target_util: float) -> np.ndarray:
    """Return servers needed for every forecast point."""
    return np.array([servers_needed(h, target_util) for h in points["high"].to_numpy(dtype=float)], dtype=int)


def needed_within(forecast: ForecastResult, until: pd.Timestamp, target_util: float) -> int:
    """Return the most servers needed by any forecast point up to `until` (0 without a forecast)."""
    if not forecast.ok:
        return 0
    pts = forecast.points[forecast.points["ts"] <= until]
    return int(needed_series(pts, target_util).max()) if len(pts) else 0


def propose(group: GroupInfo, profiles: pd.DataFrame, forecast: ForecastResult, target_util: float) -> Proposal:
    """Return the raw change: add for the next minute's need, stop an idle server, or remove what the hour won't need."""
    current = int(group.current)
    if not forecast.ok:
        return Proposal("hold", current, current)
    needed = needed_series(forecast.points, target_util)
    needed_now, needed_peak = int(needed[0]), int(needed.max())
    if needed_now > current:
        return Proposal("scale_up", current, needed_now)
    floor = max(int(group.min_size), 1)
    idle = profiles[profiles["status"] == "idle"].sort_values("p95_cpu") if len(profiles) else profiles
    if len(idle) and current - 1 >= floor and needed_peak <= current - 1:
        srv = idle.iloc[0]
        return Proposal("stop_idle", current, current - 1, int(srv["server_id"]), str(srv["name"]))
    if needed_peak < current:
        return Proposal("scale_down", current, needed_peak)
    return Proposal("hold", current, current)
