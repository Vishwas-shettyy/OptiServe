"""One or two plain sentences for a recommendation. Pure."""

from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

from app.engine.common import EngineParams, duration_words
from app.engine.forecaster import ForecastResult
from app.engine.planner import Proposal, needed_series
from app.engine.pricing import format_inr


def _servers(n: int) -> str:
    """Return '1 server' or 'N servers'."""
    return f"{n} server" if n == 1 else f"{n} servers"


def _resource(forecast: ForecastResult) -> str:
    """Return 'CPU' or 'Memory'."""
    return "Memory" if forecast.resource == "memory" else "CPU"


def _busy_now(forecast: ForecastResult, current: int) -> Optional[float]:
    """Return how busy the group will be in the next minute, in percent of current capacity."""
    if not forecast.ok or current <= 0:
        return None
    return float(forecast.points["expected"].iloc[0]) / current * 100.0


def explain(
    proposal: Proposal,
    *,
    forecast: ForecastResult,
    now: pd.Timestamp,
    target_util: float,
    params: EngineParams,
    data_span: timedelta,
    savings_inr: float,
    hold_rule: Optional[int] = None,
) -> str:
    """Return a one- or two-sentence explanation with no jargon."""
    current = proposal.from_count
    change = abs(proposal.to_count - proposal.from_count)
    if proposal.kind == "scale_up":
        pts = forecast.points
        if forecast.ok and current > 0:
            window = pts[pts["ts"] <= now + params.lead_time]
            window = window if len(window) else pts.iloc[:1]
            peak_i = int(window["expected"].to_numpy().argmax())
            peak = float(window["expected"].iloc[peak_i]) / current * 100.0
            short = np.flatnonzero(needed_series(window, target_util) > current)
            at = window["ts"].iloc[int(short[0])] if len(short) else window["ts"].iloc[peak_i]
            minutes = max(1, int(round((at - now).total_seconds() / 60)))
            when = "in about 1 minute" if minutes == 1 else f"in about {minutes} minutes"
            return (f"{_resource(forecast)} will reach {peak:.0f}% {when}. "
                    f"Add {_servers(change)} now so {'it is' if change == 1 else 'they are'} ready in time.")
        return f"Your servers are running out of room. Add {_servers(change)} now."
    if proposal.kind == "stop_idle":
        return (f"{proposal.server_name} has done almost nothing for {duration_words(params.idle_window)}. "
                f"Stop it to save {format_inr(savings_inr)}/month.")
    if proposal.kind == "scale_down":
        peak = float(forecast.points["expected"].max()) / current * 100.0 if forecast.ok and current else 0.0
        return (f"Your servers will stay under {max(peak, 1):.0f}% busy for the next hour. "
                f"Remove {_servers(change)} to save {format_inr(savings_inr)}/month.")
    if hold_rule == 7 or data_span < params.min_data:
        return (f"OptiServe is learning: {duration_words(data_span)} of data collected so far. "
                f"It will suggest changes after {duration_words(params.min_data)}.")
    if not forecast.ok:
        return "OptiServe needs a few more minutes of recent data before it can look ahead."
    if hold_rule == 8:
        return f"Load is too unpredictable right now to remove a server safely. Keeping {_servers(current)}."
    busy = _busy_now(forecast, current)
    return f"Your servers are {busy:.0f}% busy and have room for the next hour. No change needed."


def what_we_see(
    *,
    status_reason: str,
    mem_pct: Optional[float],
    provider: str,
    group_name: str,
    capacity: int,
    forecast: ForecastResult,
    now: pd.Timestamp,
    target_util: float,
    params: EngineParams,
    data_span: timedelta,
    demand_now: Optional[float],
) -> list[str]:
    """Return 3–5 plain sentences describing what OptiServe sees for one server and its group."""
    out = [status_reason]
    if mem_pct is not None and np.isfinite(mem_pct):
        out.append(f"Memory is {mem_pct:.0f}% full.")
    elif provider == "aws":
        out.append("AWS doesn't report memory. Install the agent on this server to see it.")
    if demand_now is not None and capacity > 0:
        out.append(
            f"The group {group_name} is {demand_now / capacity * 100:.0f}% busy across its {_servers(capacity)} right now."
        )
    if forecast.ok and capacity > 0:
        pts = forecast.points
        i = int(pts["expected"].to_numpy(dtype=float).argmax())
        peak = float(pts["expected"].iloc[i]) / capacity * 100.0
        minutes = max(1, int((pd.Timestamp(pts["ts"].iloc[i]) - now).total_seconds() // 60))
        aim = target_util * 100.0
        when = "in the next few minutes" if minutes <= 2 else f"in about {minutes} minutes"
        verdict = (
            f"That's above the {aim:.0f}% OptiServe aims for, so it plans more room."
            if peak > aim
            else f"That stays under the {aim:.0f}% OptiServe aims for."
        )
        out.append(f"In the next hour it is expected to peak at {peak:.0f}% busy {when}. {verdict}")
    elif not forecast.ok:
        out.append(f"OptiServe is learning: {forecast.message[len('Learning: '):] if forecast.message.startswith('Learning: ') else forecast.message}.")
    if data_span < params.min_data:
        out.append(
            f"OptiServe has {duration_words(data_span)} of numbers and waits for {duration_words(params.min_data)} "
            "before suggesting changes."
        )
    return out
