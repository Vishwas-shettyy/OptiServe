"""Safety rules on plans and alert building."""

import numpy as np
import pandas as pd

from engine import config

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _rule(rule: str, status: str, message: str) -> dict:
    """Return one guardrail result dict."""
    return {"rule": rule, "status": status, "message": message}


def _changed(before: np.ndarray, after: np.ndarray) -> int:
    """Return how many hours differ between two plans."""
    return int((before != after).sum())


def _min_servers(planned: np.ndarray) -> tuple[np.ndarray, dict]:
    """Rule 1: never plan fewer than MIN_SERVERS."""
    out = np.maximum(planned, config.MIN_SERVERS)
    n = _changed(planned, out)
    if n:
        return out, _rule("Minimum servers", "adjusted", f"Raised {n} hours to the minimum of {config.MIN_SERVERS} servers.")
    return out, _rule("Minimum servers", "pass", f"Every hour keeps at least {config.MIN_SERVERS} servers.")


def _prewarm(planned: np.ndarray) -> tuple[np.ndarray, dict]:
    """Rule 2: capacity is ready PREWARM_HOURS before demand rises."""
    window = config.PREWARM_HOURS + 1
    out = pd.Series(planned[::-1]).rolling(window, min_periods=1).max().to_numpy()[::-1].astype(int)
    n = _changed(planned, out)
    if n:
        return out, _rule("Pre-warm", "adjusted", f"Started servers {config.PREWARM_HOURS}h early in {n} hours so capacity is ready before peaks.")
    return out, _rule("Pre-warm", "pass", "No ramp-ups needed earlier starts.")


def _step_limit(planned: np.ndarray) -> tuple[np.ndarray, dict]:
    """Rule 3: remove at most MAX_STEP_DOWN servers per hour."""
    k = np.arange(len(planned))
    step = config.MAX_STEP_DOWN
    out = (np.maximum.accumulate(planned + step * k) - step * k).astype(int)
    n = _changed(planned, out)
    if n:
        return out, _rule("Step limit", "adjusted", f"Slowed {n} scale-downs to at most {step} servers removed per hour.")
    return out, _rule("Step limit", "pass", f"No hour removes more than {step} servers.")


def apply_guardrails(
    plan: pd.DataFrame,
    forecast: pd.DataFrame,
    profile_service: pd.DataFrame,
    history_days: int,
    current: int,
) -> tuple[pd.DataFrame, list[dict]]:
    """Apply safety rules in order and report each one."""
    planned = plan["planned"].to_numpy(dtype=int)
    rules = []
    for step in (_min_servers, _prewarm, _step_limit):
        planned, result = step(planned)
        rules.append(result)

    if history_days < config.MIN_HISTORY_DAYS:
        planned = np.full(len(planned), int(current))
        rules.append(_rule("Low data", "blocked", f"Only {history_days} days of history (need {config.MIN_HISTORY_DAYS}) — keeping {current} servers."))
    else:
        rules.append(_rule("Low data", "pass", f"{history_days} days of history available."))

    expected = forecast["expected"].to_numpy(dtype=float)
    spread = (forecast["high"].to_numpy(dtype=float) - forecast["low"].to_numpy(dtype=float)) / np.where(expected > 0, expected, np.nan)
    uncertainty = float(np.nanmean(spread)) if np.isfinite(spread).any() else float("inf")
    if uncertainty > config.LOW_CONFIDENCE_RATIO:
        planned = np.maximum(planned, int(current))
        rules.append(_rule("Low confidence", "blocked", f"Forecast too uncertain (band {uncertainty:.0%} of expected) — not scaling below {current} servers."))
    else:
        rules.append(_rule("Low confidence", "pass", f"Forecast band is {uncertainty:.0%} of expected — confident enough."))

    risky = profile_service.loc[profile_service["status"] == "Risky", "server_id"].tolist() if len(profile_service) else []
    if risky:
        planned = np.maximum(planned, int(current))
        names = ", ".join(risky)
        rules.append(_rule("Health", "blocked", f"{names} is unhealthy — fix it before removing servers; keeping at least {current}."))
    else:
        rules.append(_rule("Health", "pass", "All servers in this service are healthy."))

    out = plan.copy()
    out["planned"] = planned.astype(int)
    return out, rules


def _clusters(anomalies: list[dict], gap_hours: int = 3) -> list[list[dict]]:
    """Group anomalies whose timestamps are within gap_hours of each other."""
    groups: list[list[dict]] = []
    for a in sorted(anomalies, key=lambda x: x["timestamp"]):
        if groups and a["timestamp"] - groups[-1][-1]["timestamp"] <= pd.Timedelta(hours=gap_hours):
            groups[-1].append(a)
        else:
            groups.append([a])
    return groups


def build_alerts(profile: pd.DataFrame, services_results: dict) -> list[dict]:
    """Build sorted critical/warning/info alerts."""
    alerts = []
    for row in profile[profile["status"] == "Risky"].itertuples(index=False):
        alerts.append({"severity": "critical", "service": row.service, "message": f"{row.server_id} is unhealthy: {row.reason}."})

    for service, res in services_results.items():
        fc, plan = res.forecast, res.plan
        current = int(plan["current"].iloc[0])
        short = fc["high"].to_numpy() > current * config.CAPACITY_RPS * 0.9
        if short.any():
            i = int(short.argmax())
            ts = pd.Timestamp(fc["timestamp"].iloc[i])
            need = int(plan["needed_raw"].iloc[i])
            alerts.append({"severity": "warning", "service": service,
                           "message": f"Capacity shortfall expected at {ts:%a %d %b %H:%M} — needs {need} servers, you run {current}"})
        rec = getattr(res, "recommendation", None) or {}
        if rec.get("month_servers") is not None:
            weeks = float(rec["runway_weeks"])
            if weeks > 0:
                by = pd.Timestamp(fc["timestamp"].min()) + pd.Timedelta(weeks=weeks)
                when = f"in ~{weeks:.0f} week(s) (by {by:%d %b})"
            else:
                when = f"within a week (by {pd.Timestamp(fc.loc[fc['high'].idxmax(), 'timestamp']):%d %b})"
            alerts.append({"severity": "warning", "service": service,
                           "message": f"Demand growing ~{rec['growth_weekly_pct']:.0f}%/week — current capacity runs out "
                                      f"{when}. Plan {rec['month_servers']} servers for next month."})
        for group in _clusters(res.anomalies):
            peak = max(group, key=lambda a: a["value"])
            ratio = peak["value"] / peak["expected"] if peak["expected"] > 0 else float("inf")
            alerts.append({"severity": "warning", "service": service,
                           "message": f"Unusual traffic at {peak['timestamp']:%a %d %b %H:%M} — {ratio:.1f}× normal ({len(group)} hour(s)); excluded from the forecast"})

    zombies = profile[profile["status"] == "Zombie"]
    if len(zombies):
        cost = float(zombies["monthly_cost"].sum())
        alerts.append({"severity": "info", "service": ", ".join(sorted(zombies["service"].unique())),
                       "message": f"{len(zombies)} zombie server(s) cost {config.CURRENCY}{cost:,.0f}/month doing nothing"})

    return sorted(alerts, key=lambda a: SEVERITY_ORDER[a["severity"]])
