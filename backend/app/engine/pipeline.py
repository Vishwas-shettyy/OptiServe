"""profile → short forecast → plan → guardrails → explain for one group. Pure: DataFrames in, a Decision out."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from app.engine.common import DEFAULT_RISK, EngineParams, normalize_metrics, risk_params, utc
from app.engine.explainer import explain
from app.engine.forecaster import ForecastResult, band_ratio, group_demand, short_forecast
from app.engine.guardrails import GuardContext, GuardrailResult, apply_guardrails
from app.engine.planner import GroupInfo, Proposal, propose
from app.engine.pricing import hourly_usd, monthly_inr
from app.engine.profiler import profile_servers


@dataclass
class Decision:
    """The recommendation for a group plus everything the UI's 'Details' needs."""

    group_id: int
    kind: str
    from_count: int
    to_count: int
    server_id: Optional[int]
    reason: str
    savings_month_inr: float
    confidence: float
    status: str
    blocked_reason: Optional[str]
    executable: bool
    guardrails: list[GuardrailResult]
    forecast: ForecastResult
    profiles: pd.DataFrame

    def to_record(self) -> dict:
        """Return the fields of a Recommendation row."""
        return {
            "group_id": self.group_id, "server_id": self.server_id, "kind": self.kind,
            "from_count": self.from_count, "to_count": self.to_count, "reason": self.reason,
            "savings_month_inr": self.savings_month_inr, "confidence": self.confidence,
            "status": self.status, "blocked_reason": self.blocked_reason,
        }


def _price(row: dict) -> float:
    """Return a server's hourly USD price (override, table, else 0)."""
    return hourly_usd(row.get("instance_type"), row.get("hourly_cost_usd")) or 0.0


def savings_month_inr(p: Proposal, servers: pd.DataFrame, usd_inr: float) -> float:
    """Return monthly INR saved (negative = extra cost) by the change."""
    if p.kind == "hold" or servers.empty:
        return 0.0
    rows = servers.to_dict("records")
    if p.kind == "stop_idle" and p.server_id is not None:
        match = [r for r in rows if r["server_id"] == p.server_id]
        price = _price(match[0]) if match else 0.0
    else:
        price = float(np.mean([_price(r) for r in rows]))
    return monthly_inr(price, usd_inr, p.from_count - p.to_count)


def confidence(forecast: ForecastResult) -> float:
    """Return 0–1 confidence from how narrow the forecast band is."""
    ratio = band_ratio(forecast)
    return 0.0 if not np.isfinite(ratio) else round(float(np.clip(1.0 - ratio / 2.0, 0.0, 1.0)), 3)


def evaluate_group(
    group: GroupInfo,
    servers: pd.DataFrame,
    metrics: pd.DataFrame,
    now: datetime,
    params: EngineParams,
    risk: float = DEFAULT_RISK,
    last_action_at: Optional[datetime] = None,
    usd_inr: float = 83.0,
) -> Decision:
    """Run the full engine for one group's running servers and their MetricPoint rows."""
    now_ts = utc(now)
    srv = servers
    if "group_id" in srv.columns:
        srv = srv[srv["group_id"] == group.group_id]
    if "state" in srv.columns:
        srv = srv[srv["state"] != "stopped"]
    m = normalize_metrics(metrics)
    m = m[m["server_id"].isin(srv["server_id"]) & (m["ts"] <= now_ts)]
    target_util, z = risk_params(risk)
    profiles = profile_servers(m, srv, now_ts, params)
    forecast = short_forecast(group_demand(m), now_ts, params, z)
    span = (now_ts - m["ts"].min()).to_pytimedelta() if len(m) else timedelta(0)
    ctx = GuardContext(group, now_ts, params, target_util, forecast, span, profiles, last_action_at)
    outcome = apply_guardrails(propose(group, profiles, forecast, target_util), ctx)
    p = outcome.proposal
    saving = savings_month_inr(p, srv, usd_inr)
    reason = explain(p, forecast=forecast, now=now_ts, target_util=target_util, params=params,
                     data_span=span, savings_inr=saving, hold_rule=outcome.hold_rule)
    return Decision(
        group_id=group.group_id, kind=p.kind, from_count=p.from_count, to_count=p.to_count, server_id=p.server_id,
        reason=reason, savings_month_inr=saving, confidence=confidence(forecast), status=outcome.status,
        blocked_reason=outcome.blocked_reason, executable=outcome.executable and outcome.status != "blocked",
        guardrails=outcome.results, forecast=forecast, profiles=profiles,
    )
