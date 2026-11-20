"""Turn a forecast into servers per hour and a recommendation."""

import math

import numpy as np
import pandas as pd

from engine import config

PLAN_COLUMNS = ["timestamp", "needed_raw", "planned", "current"]


def needed_servers(forecast: pd.DataFrame, capacity_rps: float, target_util: float) -> pd.Series:
    """Return servers needed per forecast hour (CPU or memory, whichever is larger)."""
    cpu = np.ceil(forecast["high"].to_numpy(dtype=float) / (capacity_rps * target_util) - 1e-9)
    mem = np.ceil(forecast["mem_high"].to_numpy(dtype=float) / target_util - 1e-9)
    needed = np.maximum(np.maximum(cpu, mem), config.MIN_SERVERS).astype(int)
    return pd.Series(needed, index=forecast.index, name="needed_raw")


def build_plan(forecast: pd.DataFrame, current: int, capacity_rps: float, target_util: float) -> pd.DataFrame:
    """Build the raw hourly plan before guardrails."""
    needed = needed_servers(forecast, capacity_rps, target_util).to_numpy()
    return pd.DataFrame({
        "timestamp": forecast["timestamp"].to_numpy(),
        "needed_raw": needed,
        "planned": needed.copy(),
        "current": np.full(len(needed), int(current)),
    })[PLAN_COLUMNS]


def _action(planned_max: int, planned_avg: float, current: int) -> str:
    """Return scale_up, scale_down, schedule or hold."""
    up = planned_max > current
    down_avg = planned_avg < 0.9 * current
    if up and not down_avg:
        return "scale_up"
    if not up and down_avg:
        return "scale_down"
    if up and down_avg:
        return "schedule"
    return "hold"


def recommend(plan: pd.DataFrame, monthly_cost: float, current: int) -> dict:
    """Summarise a plan into a recommendation dict."""
    planned = plan["planned"].astype(int)
    planned_avg = float(planned.mean())
    current_monthly = float(current) * float(monthly_cost)
    planned_monthly = planned_avg * float(monthly_cost)
    savings = current_monthly - planned_monthly
    peak_i = int(plan["needed_raw"].to_numpy().argmax())
    quiet_i = int(plan["needed_raw"].to_numpy().argmin())
    return {
        "current": int(current),
        "planned_min": int(planned.min()),
        "planned_avg": round(planned_avg, 2),
        "planned_max": int(planned.max()),
        "current_monthly": round(current_monthly, 2),
        "planned_monthly": round(planned_monthly, 2),
        "savings_monthly": round(savings, 2),
        "savings_pct": round(savings / current_monthly * 100.0, 1) if current_monthly > 0 else 0.0,
        "action": _action(int(planned.max()), planned_avg, int(current)),
        "peak_time": pd.Timestamp(plan["timestamp"].iloc[peak_i]),
        "peak_servers": int(planned.iloc[peak_i]),
        "quiet_time": pd.Timestamp(plan["timestamp"].iloc[quiet_i]),
    }


def next_month_outlook(growth_weekly: float, forecast: pd.DataFrame, current: int, capacity_rps: float,
                       target_util: float) -> dict:
    """Return growth_weekly_pct, runway_weeks and month_servers for a growing service (all None otherwise)."""
    none = {"growth_weekly_pct": None, "runway_weeks": None, "month_servers": None}
    if growth_weekly <= config.GROWTH_MIN_WEEKLY or forecast.empty:
        return none
    peak = float(forecast["high"].max())
    usable = current * capacity_rps * target_util
    per_server = capacity_rps * target_util
    if peak <= 0 or per_server <= 0:
        return none
    runway = 0.0 if peak >= usable else math.log(usable / peak) / math.log(growth_weekly)
    return {
        "growth_weekly_pct": round((growth_weekly - 1.0) * 100.0, 1),
        "runway_weeks": round(runway, 1),
        "month_servers": int(math.ceil(peak * growth_weekly ** config.WEEKS_PER_MONTH / per_server)),
    }
