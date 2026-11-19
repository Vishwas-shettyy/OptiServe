"""Time machine: backtest the planner on the last history week."""

import numpy as np
import pandas as pd

from engine import config
from engine.forecaster import forecast_service, naive_forecast, wape
from engine.guardrails import apply_guardrails
from engine.planner import build_plan

TEST_HOURS = 7 * 24


def _hours(actual: np.ndarray, servers: np.ndarray, capacity_rps: float) -> tuple[int, int]:
    """Return (shortfall hours, over-provisioned hours) for a capacity series."""
    capacity = servers * capacity_rps
    shortfall = int((actual > capacity).sum())
    overprov = int((actual / capacity < config.OVERPROV_UTIL).sum())
    return shortfall, overprov


def run_backtest(
    history: pd.DataFrame,
    events: pd.DataFrame,
    current: int,
    capacity_rps: float,
    monthly_cost: float,
    risk: float,
) -> dict:
    """Compare planned vs fixed capacity on the held-out week."""
    hist = history.sort_values("timestamp").reset_index(drop=True)
    split = hist["timestamp"].min() + pd.Timedelta(days=config.TRAIN_DAYS)
    train = hist[hist["timestamp"] < split]
    test = hist[hist["timestamp"] >= split].iloc[:TEST_HOURS]
    params = config.risk_params(risk)
    fc, _ = forecast_service(train, events, split, len(test), params["z"])
    raw = build_plan(fc, current, capacity_rps, params["target_util"])
    no_health = pd.DataFrame(columns=["server_id", "status"])
    plan, _ = apply_guardrails(raw, fc, no_health, config.TRAIN_DAYS, current)
    actual = test["requests"].to_numpy(dtype=float)
    planned = plan["planned"].to_numpy(dtype=int)
    fixed = np.full(len(actual), int(current))
    hourly = monthly_cost / config.HOURS_PER_MONTH
    cost_fixed = float(fixed.sum() * hourly)
    cost_plan = float(planned.sum() * hourly)
    short_f, over_f = _hours(actual, fixed, capacity_rps)
    short_p, over_p = _hours(actual, planned, capacity_rps)
    naive = naive_forecast(train, split, len(test))
    series = pd.DataFrame({
        "timestamp": test["timestamp"].to_numpy(),
        "actual": actual,
        "capacity_fixed": fixed * capacity_rps,
        "capacity_plan": planned * capacity_rps,
    })
    return {
        "cost_fixed": round(cost_fixed, 2),
        "cost_plan": round(cost_plan, 2),
        "savings_pct": round((cost_fixed - cost_plan) / cost_fixed * 100.0, 1) if cost_fixed > 0 else 0.0,
        "shortfall_hours_fixed": short_f,
        "shortfall_hours_plan": short_p,
        "overprov_hours_fixed": over_f,
        "overprov_hours_plan": over_p,
        "wape_optiserve": round(wape(actual, fc["expected"]), 4),
        "wape_naive": round(wape(actual, naive), 4),
        "series": series,
    }
