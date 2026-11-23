"""Engine v2: scenario tests on generated fixtures plus unit tests for each pure module."""

import ast
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.engine.accuracy import accuracy_pct, score_forecasts
from app.engine.common import params_for, risk_params
from app.engine.forecaster import group_demand, plan_forecast, short_forecast
from app.engine.pipeline import evaluate_group
from app.engine.planner import servers_needed
from app.engine.pricing import format_inr, hourly_usd, monthly_inr
from app.engine.profiler import profile_servers
from tests.fixtures.engine_data import (
    NOW, group, idle_server, quiet_group, rising_load, server_metrics, servers_frame,
)

NORMAL = params_for(False)
LIVE = params_for(True)


def _rule(decision, number: int):
    """Return one guardrail result by rule number."""
    return next(r for r in decision.guardrails if r.number == number)


def test_rising_load_scales_up_before_threshold_within_lead_time() -> None:
    """Load still fits now, but will not within 30 minutes: add a server now."""
    metrics = rising_load()
    latest = metrics[metrics["ts"] == NOW]["cpu_pct"].mean()
    assert latest < 70  # still below the 70% target right now
    d = evaluate_group(group(3), servers_frame([1, 2, 3]), metrics, NOW, NORMAL)
    assert d.kind == "scale_up" and d.from_count == 3 and d.to_count == 4
    assert _rule(d, 3).status == "adjusted"
    assert d.status == "pending" and d.executable
    assert "Add 1 server now" in d.reason and "minutes" in d.reason
    assert d.savings_month_inr < 0


def test_rising_load_outside_short_lead_time_holds() -> None:
    """With a 5-minute lead time the same rise is not urgent yet."""
    d = evaluate_group(group(3), servers_frame([1, 2, 3]), rising_load(), NOW, LIVE)
    assert d.kind == "hold"


def test_idle_server_gets_stop_idle() -> None:
    """A server idle for the whole 7-day window is recommended to stop."""
    d = evaluate_group(group(3), servers_frame([1, 2, 3]), idle_server(), NOW, NORMAL)
    assert d.kind == "stop_idle" and d.server_id == 3 and d.to_count == 2
    assert d.savings_month_inr == pytest.approx(monthly_inr(0.0416, 83.0), rel=1e-6)
    assert d.executable and d.status == "pending"
    assert "web-3" in d.reason and "₹" in d.reason
    assert d.profiles.set_index("server_id").loc[3, "status"] == "idle"


def test_idle_server_not_stopped_below_group_min() -> None:
    """stop_idle only when the group keeps its minimum."""
    d = evaluate_group(group(3, min_size=3), servers_frame([1, 2, 3]), idle_server(), NOW, NORMAL)
    assert d.kind == "hold"


@pytest.mark.parametrize("cause", ["memory", "silent", "status_check"])
def test_unhealthy_server_blocks_scale_down(cause: str) -> None:
    """Any unhealthy server blocks removing capacity, with the reason in plain words."""
    frames = [server_metrics(i, pd.Timedelta(hours=26), 15.0, mem=20.0) for i in (1, 2, 3)]
    checks = [True] * 4
    if cause == "memory":
        frames.append(server_metrics(4, pd.Timedelta(hours=26), 15.0, mem=95.0))
    elif cause == "silent":
        frames.append(server_metrics(4, pd.Timedelta(hours=26), 15.0, mem=20.0, end=NOW - pd.Timedelta(minutes=5)))
    else:
        frames.append(server_metrics(4, pd.Timedelta(hours=26), 15.0, mem=20.0))
        checks[3] = False
    servers = servers_frame([1, 2, 3, 4], status_check_ok=checks)
    d = evaluate_group(group(4), servers, pd.concat(frames, ignore_index=True), NOW, NORMAL)
    assert d.kind == "scale_down" and d.to_count == 3
    assert d.status == "blocked" and not d.executable
    assert _rule(d, 6).status == "blocked"
    assert "web-4" in d.blocked_reason and "removing servers" in d.blocked_reason


def test_low_data_holds() -> None:
    """Two hours of data (need 24) means hold and say OptiServe is learning."""
    metrics = quiet_group(3, span=pd.Timedelta(hours=2))
    d = evaluate_group(group(3), servers_frame([1, 2, 3]), metrics, NOW, NORMAL)
    assert d.kind == "hold" and d.from_count == d.to_count == 3
    assert _rule(d, 7).status == "blocked"
    assert "learning" in d.reason.lower()
    assert not d.executable


def test_unmanaged_group_is_recommendation_only() -> None:
    """Without the managed tag the advice stands but cannot be executed."""
    d = evaluate_group(group(3, managed=False), servers_frame([1, 2, 3]), idle_server(), NOW, NORMAL)
    assert d.kind == "stop_idle" and d.status == "pending"
    assert not d.executable
    assert _rule(d, 9).status == "blocked" and "recommendation only" in _rule(d, 9).message


def test_agent_group_is_recommendation_only() -> None:
    """Agent-only groups are never executed."""
    d = evaluate_group(group(3, provider="agent"), servers_frame([1, 2, 3]), idle_server(), NOW, NORMAL)
    assert d.kind == "stop_idle" and not d.executable


def test_step_limit_removes_one_server_at_a_time() -> None:
    """Five near-empty servers need one, but only one is removed per action."""
    d = evaluate_group(group(5), servers_frame([1, 2, 3, 4, 5]), quiet_group(5, mem=None), NOW, NORMAL)
    assert d.kind == "scale_down" and d.from_count == 5 and d.to_count == 4
    assert _rule(d, 4).status == "adjusted"
    assert d.executable and d.savings_month_inr > 0


def test_cooldown_blocks_then_allows() -> None:
    """A change 5 minutes ago blocks; 20 minutes ago passes."""
    args = (group(5), servers_frame([1, 2, 3, 4, 5]), quiet_group(5, mem=None), NOW, NORMAL)
    recent = evaluate_group(*args, last_action_at=NOW - timedelta(minutes=5))
    assert recent.status == "blocked" and _rule(recent, 5).status == "blocked"
    assert "Waiting 10 minutes" in recent.blocked_reason
    later = evaluate_group(*args, last_action_at=NOW - timedelta(minutes=20))
    assert later.status == "pending" and _rule(later, 5).status == "pass"


def test_max_servers_blocks_when_already_at_max() -> None:
    """Needing more than the group max is blocked with a clear message."""
    d = evaluate_group(group(3, max_size=3), servers_frame([1, 2, 3]), rising_load(), NOW, NORMAL)
    assert d.status == "blocked" and "maximum is 3" in d.blocked_reason


def test_all_nine_rules_reported() -> None:
    """Every decision lists rules 1–9 in order."""
    d = evaluate_group(group(3), servers_frame([1, 2, 3]), idle_server(), NOW, NORMAL)
    assert [r.number for r in d.guardrails] == list(range(1, 10))
    assert all(r.status in ("pass", "adjusted", "blocked") and r.message for r in d.guardrails)


def test_profiler_statuses() -> None:
    """Busy, normal, idle and unhealthy are told apart."""
    span = pd.Timedelta(days=8)
    metrics = pd.concat([
        server_metrics(1, span, 90.0), server_metrics(2, span, 40.0),
        server_metrics(3, span, 1.0, net=5.0), server_metrics(4, span, 40.0, mem=96.0),
    ], ignore_index=True)
    prof = profile_servers(metrics, servers_frame([1, 2, 3, 4]), NOW, NORMAL).set_index("server_id")
    assert prof["status"].to_dict() == {1: "busy", 2: "normal", 3: "idle", 4: "unhealthy"}


def test_idle_needs_full_window() -> None:
    """A server quiet for only 2 days is not idle under the 7-day window, but is in live mode."""
    metrics = server_metrics(1, pd.Timedelta(days=2), 1.0, net=5.0)
    assert profile_servers(metrics, servers_frame([1]), NOW, NORMAL)["status"].iloc[0] == "normal"
    assert profile_servers(metrics, servers_frame([1]), NOW, LIVE)["status"].iloc[0] == "idle"


def test_demand_uses_higher_resource() -> None:
    """Demand is max(Σcpu, Σmem)/100."""
    metrics = pd.concat([server_metrics(i, pd.Timedelta(minutes=30), 20.0, mem=60.0, noise=0) for i in (1, 2)])
    d = group_demand(metrics)
    assert d["demand"].iloc[-1] == pytest.approx(1.2) and d["resource"].iloc[-1] == "memory"


def test_short_forecast_follows_trend() -> None:
    """Holt extrapolates a clean linear rise."""
    ts = pd.date_range(NOW - pd.Timedelta(minutes=59), NOW, freq="min")
    demand = pd.DataFrame({"ts": ts, "demand": np.linspace(1.0, 1.59, 60), "resource": "cpu"})
    fc = short_forecast(demand, NOW, NORMAL, z=1.25)
    assert fc.ok and len(fc.points) == 60
    assert fc.points["expected"].iloc[29] == pytest.approx(1.89, abs=0.02)
    assert (fc.points["high"] >= fc.points["expected"]).all()


def test_short_forecast_learning_without_recent_data() -> None:
    """Fewer than 10 recent minutes → learning."""
    ts = pd.date_range(NOW - pd.Timedelta(minutes=4), NOW, freq="min")
    fc = short_forecast(pd.DataFrame({"ts": ts, "demand": 1.0, "resource": "cpu"}), NOW, NORMAL, 1.25)
    assert fc.status == "learning" and fc.points.empty


def _hourly(days: int) -> pd.DataFrame:
    """Hourly demand with a daily cycle."""
    ts = pd.date_range(NOW - pd.Timedelta(days=days), NOW - pd.Timedelta(hours=1), freq="h")
    values = 2.0 + np.sin(2 * np.pi * ts.hour.to_numpy() / 24)
    return pd.DataFrame({"ts": ts, "demand": values, "resource": "cpu"})


def test_plan_forecast_learning_under_seven_days() -> None:
    """Under 7 days the plan forecast reports progress instead of numbers."""
    fc = plan_forecast(_hourly(3), NOW, NORMAL, 1.25)
    assert fc.status == "learning" and fc.message == "Learning: 3 of 7 days collected"


def test_plan_forecast_seven_days_hourly() -> None:
    """With 14 days the plan forecast gives 168 hourly points that track the cycle."""
    fc = plan_forecast(_hourly(14), NOW, NORMAL, 1.25)
    assert fc.ok and len(fc.points) == 168
    truth = 2.0 + np.sin(2 * np.pi * fc.points["ts"].dt.hour.to_numpy() / 24)
    assert accuracy_pct(truth, fc.points["expected"].to_numpy()) > 95


def test_planner_and_risk() -> None:
    """ceil(high / target_util) with target_util from risk."""
    assert risk_params(0.5)[0] == pytest.approx(0.70)
    assert risk_params(0.0)[0] == pytest.approx(0.85) and risk_params(1.0)[0] == pytest.approx(0.55)
    assert servers_needed(2.1, 0.70) == 3 and servers_needed(2.11, 0.70) == 4 and servers_needed(0.0, 0.7) == 1


def test_accuracy_scoring() -> None:
    """Accuracy is 100 − WAPE over matched minutes in the last 24 h."""
    ts = pd.date_range(NOW - pd.Timedelta(minutes=9), NOW, freq="min")
    actual = pd.DataFrame({"ts": ts, "demand": 2.0})
    forecast = pd.DataFrame({"ts": ts, "expected": 1.8})
    assert score_forecasts(forecast, actual, NOW) == {"accuracy_pct": 90.0, "wape": 0.1, "points": 10}
    old = forecast.assign(ts=forecast["ts"] - pd.Timedelta(days=2))
    assert score_forecasts(old, actual, NOW)["accuracy_pct"] is None


def test_pricing() -> None:
    """Table lookup, per-server override and Indian rupee formatting."""
    assert hourly_usd("t3.medium") == 0.0416
    assert hourly_usd("t3.medium", 0.05) == 0.05
    assert hourly_usd("x9.huge") is None
    assert monthly_inr(0.1, 83.0, 2) == pytest.approx(0.1 * 83 * 730 * 2)
    assert format_inr(420000) == "₹4,20,000" and format_inr(4200) == "₹4,200" and format_inr(-950) == "-₹950"


def test_engine_has_no_db_or_network_imports() -> None:
    """engine/ stays pure: no DB, AWS, HTTP or app I/O modules."""
    banned = {"sqlmodel", "sqlalchemy", "boto3", "botocore", "httpx", "requests", "socket", "urllib", "fastapi"}
    banned_app = {"app.db", "app.models", "app.config", "app.connectors", "app.actions", "app.api", "app.jobs"}
    for path in (Path(__file__).parent.parent / "app" / "engine").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert name.split(".")[0] not in banned, f"{path.name} imports {name}"
                assert not any(name == b or name.startswith(b + ".") for b in banned_app), f"{path.name} imports {name}"
