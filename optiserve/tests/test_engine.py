"""Engine tests."""

import importlib

import numpy as np
import pandas as pd
import pytest

ENGINE_MODULES = [
    "config", "data_gen", "profiler", "forecaster", "planner",
    "guardrails", "backtest", "explainer", "pipeline",
]


def test_imports_and_risk_params() -> None:
    """All engine modules import; risk_params endpoints match presets."""
    for name in ENGINE_MODULES:
        importlib.import_module(f"engine.{name}")
    from engine.config import RISK_CHEAP, RISK_SAFE, risk_params
    assert risk_params(0) == pytest.approx(RISK_CHEAP)
    assert risk_params(1) == pytest.approx(RISK_SAFE)


from engine import data_gen
from engine.data_gen import list_scenarios, load_scenario

KEYS = [k for k, _ in list_scenarios()]


@pytest.mark.parametrize("key", KEYS)
def test_scenario_shape_and_columns(key: str) -> None:
    """Every server has 672 hourly timestamps and columns match section 3."""
    sc = load_scenario(key)
    assert list(sc.servers.columns) == data_gen.SERVER_COLUMNS
    assert list(sc.metrics.columns) == data_gen.METRIC_COLUMNS
    assert list(sc.events.columns) == data_gen.EVENT_COLUMNS
    counts = sc.metrics.groupby("server_id")["timestamp"].nunique()
    assert set(counts.index) == set(sc.servers["server_id"])
    assert (counts == 672).all()
    ts = sc.metrics["timestamp"].drop_duplicates().sort_values()
    assert (ts.diff().dropna() == pd.Timedelta(hours=1)).all()
    assert ts.iloc[0] == pd.Timestamp("2026-10-19 00:00")
    assert ts.iloc[-1] == pd.Timestamp("2026-11-15 23:00")


def test_current_servers() -> None:
    """current_servers counts non-zombie servers per active service."""
    assert load_scenario("office_hours").current_servers == {"hr-portal": 12}
    assert load_scenario("sick_server").current_servers == {"payments-api": 8}


def test_flash_sale_events() -> None:
    """Flash sale has both past and future sales as events."""
    ev = load_scenario("flash_sale").events
    starts = set(ev["start"])
    assert pd.Timestamp("2026-11-12 18:00") in starts
    assert pd.Timestamp("2026-11-20 18:00") in starts
    assert sorted(ev["multiplier"]) == [5.0, 6.0]


def test_sick_server_memory_and_spike() -> None:
    """pay-07 leaks memory above 90% in the last 24h; spike exists."""
    m = load_scenario("sick_server").metrics
    last = m["timestamp"].max() - pd.Timedelta(hours=23)
    pay7 = m[(m["server_id"] == "pay-07") & (m["timestamp"] >= last)]
    assert pay7["mem_pct"].max() > 90
    assert (pay7["error_rate"] == 0.08).all()
    pay1 = m[m["server_id"] == "pay-01"].set_index("timestamp")["requests"]
    spike = pay1[pd.Timestamp("2026-10-29 14:00")]
    assert spike > 3 * pay1[pd.Timestamp("2026-10-22 14:00")]


@pytest.mark.parametrize("key", ["office_hours", "flash_sale", "forgotten_servers"])
def test_zombie_cpu_low(key: str) -> None:
    """Zombie servers never exceed 5% CPU."""
    m = load_scenario(key).metrics
    assert (m.loc[m["service"] == "legacy", "cpu_pct"] < 5).all()


@pytest.mark.parametrize("key", KEYS)
def test_deterministic(key: str) -> None:
    """Two loads give identical data."""
    a, b = load_scenario(key), load_scenario(key)
    pd.testing.assert_frame_equal(a.metrics, b.metrics)
    pd.testing.assert_frame_equal(a.servers, b.servers)
    pd.testing.assert_frame_equal(a.events, b.events)
    assert a.current_servers == b.current_servers


from engine.profiler import PROFILE_COLUMNS, profile_servers, waste_score


def _profile(key: str) -> pd.DataFrame:
    """Profile a scenario's servers."""
    sc = load_scenario(key)
    return profile_servers(sc.metrics, sc.servers)


def test_profile_columns() -> None:
    """Profile has section 6 columns, one row per server."""
    sc = load_scenario("office_hours")
    p = profile_servers(sc.metrics, sc.servers)
    assert list(p.columns) == PROFILE_COLUMNS
    assert len(p) == len(sc.servers)


def test_office_hours_profile() -> None:
    """Legacy servers are Zombies; most hr-portal servers are Wasteful."""
    p = _profile("office_hours")
    legacy = p[p["service"] == "legacy"]
    assert len(legacy) == 2 and (legacy["status"] == "Zombie").all()
    assert legacy["idle_since"].notna().all()
    assert (legacy["wasted_monthly"] == legacy["monthly_cost"]).all()
    hr = p[p["service"] == "hr-portal"]
    assert (hr["status"] == "Wasteful").sum() > len(hr) / 2


def test_forgotten_servers_profile() -> None:
    """Exactly 5 Zombies and waste score above 25."""
    p = _profile("forgotten_servers")
    assert (p["status"] == "Zombie").sum() == 5
    assert waste_score(p) > 25


def test_sick_server_profile() -> None:
    """pay-07 is Risky."""
    p = _profile("sick_server").set_index("server_id")
    assert p.loc["pay-07", "status"] == "Risky"
    assert "memory" in p.loc["pay-07", "reason"].lower()


def _forecast(key: str) -> tuple:
    """Return (scenario, demand, forecast, anomalies) for a scenario's first service."""
    from engine import config
    from engine.data_gen import load_scenario
    from engine.forecaster import forecast_service, service_demand

    sc = load_scenario(key)
    demand = service_demand(sc.metrics, sc.servers)
    service = next(iter(sc.current_servers))
    hist = demand[demand["service"] == service]
    start = hist["timestamp"].max() + pd.Timedelta(hours=1)
    fc, anomalies = forecast_service(hist, sc.events, start, config.FORECAST_HOURS)
    return sc, hist, fc, anomalies


@pytest.mark.parametrize("key", ["office_hours", "flash_sale", "forgotten_servers", "sick_server"])
def test_forecast_shape_and_bands(key: str) -> None:
    """Forecast has 168 rows, the section 3 columns and low <= expected <= high."""
    _, hist, fc, _ = _forecast(key)
    assert list(fc.columns) == ["timestamp", "expected", "low", "high", "mem_high", "is_event"]
    assert len(fc) == 168
    assert fc["timestamp"].iloc[0] == pd.Timestamp("2026-11-16 00:00")
    assert (fc["low"] <= fc["expected"]).all() and (fc["expected"] <= fc["high"]).all()
    assert (fc["low"] >= 0).all()
    assert set(hist.columns) == {"timestamp", "service", "requests", "mem_load_eq"}


def test_flash_sale_forecast_event() -> None:
    """Festive sale hour high is at least 4x the same hour the day before."""
    _, _, fc, _ = _forecast("flash_sale")
    high = fc.set_index("timestamp")["high"]
    assert high[pd.Timestamp("2026-11-20 20:00")] >= 4 * high[pd.Timestamp("2026-11-19 20:00")]
    assert fc.set_index("timestamp").loc[pd.Timestamp("2026-11-20 20:00"), "is_event"]


def test_sick_server_spike_anomaly() -> None:
    """The payments spike at 2026-10-29 14:00 is detected as an anomaly."""
    _, _, _, anomalies = _forecast("sick_server")
    stamps = {a["timestamp"] for a in anomalies}
    assert pd.Timestamp("2026-10-29 14:00") in stamps
    assert all(set(a) == {"timestamp", "value", "expected"} for a in anomalies)


def test_naive_and_wape() -> None:
    """Naive forecast repeats last week; wape is zero for a perfect forecast."""
    from engine.forecaster import naive_forecast, wape

    _, hist, _, _ = _forecast("office_hours")
    start = pd.Timestamp("2026-11-09 00:00")
    naive = naive_forecast(hist[hist["timestamp"] < start], start, 168)
    expected = hist.set_index("timestamp")["requests"].loc["2026-11-02":"2026-11-08"].to_numpy()
    assert len(naive) == 168 and (naive.to_numpy() == expected).all()
    assert wape(pd.Series([10.0, 20.0]), pd.Series([10.0, 20.0])) == 0.0
    assert wape(pd.Series([10.0, 10.0]), pd.Series([5.0, 15.0])) == 0.5


def _planned(key: str, risk: float = 0.5) -> tuple:
    """Return (scenario, forecast, raw plan, guarded plan, rules) for a scenario's first service."""
    from engine import config
    from engine.data_gen import load_scenario
    from engine.forecaster import forecast_service, service_demand
    from engine.guardrails import apply_guardrails
    from engine.planner import build_plan
    from engine.profiler import profile_servers

    sc = load_scenario(key)
    params = config.risk_params(risk)
    demand = service_demand(sc.metrics, sc.servers)
    service = next(iter(sc.current_servers))
    hist = demand[demand["service"] == service]
    start = hist["timestamp"].max() + pd.Timedelta(hours=1)
    fc, _ = forecast_service(hist, sc.events, start, config.FORECAST_HOURS, params["z"])
    current = sc.current_servers[service]
    raw = build_plan(fc, current, config.CAPACITY_RPS, params["target_util"])
    profile = profile_servers(sc.metrics, sc.servers)
    days = int(round((hist["timestamp"].max() - hist["timestamp"].min()) / pd.Timedelta(days=1))) + 1
    plan, rules = apply_guardrails(raw, fc, profile[profile["service"] == service], days, current)
    return sc, fc, raw, plan, rules


def test_plan_columns_and_recommendation() -> None:
    """Plan matches section 3 and recommend returns every section 8 key."""
    from engine.planner import recommend

    _, _, raw, plan, rules = _planned("office_hours")
    assert list(plan.columns) == ["timestamp", "needed_raw", "planned", "current"] and len(plan) == 168
    assert [r["rule"] for r in rules] == ["Minimum servers", "Pre-warm", "Step limit", "Low data", "Low confidence", "Health"]
    assert all(r["status"] in {"pass", "adjusted", "blocked"} and r["message"] for r in rules)
    rec = recommend(plan, 7000.0, 12)
    assert set(rec) == {"current", "planned_min", "planned_avg", "planned_max", "current_monthly", "planned_monthly",
                        "savings_monthly", "savings_pct", "action", "peak_time", "peak_servers", "quiet_time"}
    assert rec["savings_monthly"] > 0 and rec["action"] in {"scale_down", "schedule"}


def test_office_hours_night_plan() -> None:
    """hr-portal needs at most 3 servers 00:00–05:00 on forecast weekdays."""
    _, _, _, plan, _ = _planned("office_hours")
    ts = plan["timestamp"].dt
    night = plan[(ts.day_of_week < 5) & (ts.hour <= 5)]
    assert len(night) == 30 and (night["planned"] <= 3).all()


def test_flash_sale_plan() -> None:
    """The festive sale hour is planned above today's 10 servers."""
    _, _, _, plan, _ = _planned("flash_sale")
    assert plan.set_index("timestamp").loc[pd.Timestamp("2026-11-20 18:00"), "planned"] > 10


def test_sick_server_health_blocks() -> None:
    """A Risky server blocks scale-down below current."""
    _, _, _, plan, rules = _planned("sick_server")
    health = next(r for r in rules if r["rule"] == "Health")
    assert health["status"] == "blocked" and "pay-07" in health["message"]
    assert plan["planned"].min() >= 8


@pytest.mark.parametrize("key", ["office_hours", "flash_sale", "forgotten_servers", "sick_server"])
@pytest.mark.parametrize("risk", [0.0, 1.0])
def test_guardrail_invariants(key: str, risk: float) -> None:
    """Planned never drops below MIN_SERVERS nor by more than MAX_STEP_DOWN per hour."""
    from engine import config

    _, _, _, plan, _ = _planned(key, risk)
    planned = plan["planned"].to_numpy()
    assert planned.min() >= config.MIN_SERVERS
    assert (np.diff(planned) >= -config.MAX_STEP_DOWN).all()


def test_guardrail_low_data_and_confidence() -> None:
    """Low data holds current; a wide forecast band blocks scale-down."""
    from engine.guardrails import apply_guardrails

    _, fc, raw, _, _ = _planned("office_hours")
    empty = pd.DataFrame(columns=["server_id", "status"])
    plan, rules = apply_guardrails(raw, fc, empty, 3, 12)
    assert (plan["planned"] == 12).all() and rules[3]["status"] == "blocked"
    wide = fc.assign(low=0.0, high=fc["expected"] * 3)
    plan, rules = apply_guardrails(raw, wide, empty, 28, 12)
    assert plan["planned"].min() >= 12 and rules[4]["status"] == "blocked"


def test_build_alerts() -> None:
    """Alerts include critical pay-07, zombie info and are sorted by severity."""
    from types import SimpleNamespace

    from engine.guardrails import build_alerts
    from engine.profiler import profile_servers

    sc, fc, _, plan, _ = _planned("flash_sale")
    res = {"shop-web": SimpleNamespace(forecast=fc, plan=plan, anomalies=[])}
    alerts = build_alerts(profile_servers(sc.metrics, sc.servers), res)
    assert any(a["severity"] == "warning" and "Capacity shortfall expected" in a["message"] for a in alerts)
    assert alerts[-1]["severity"] == "info"
    sc, fc, _, plan, _ = _planned("sick_server")
    res = {"payments-api": SimpleNamespace(forecast=fc, plan=plan, anomalies=[])}
    alerts = build_alerts(profile_servers(sc.metrics, sc.servers), res)
    assert alerts[0]["severity"] == "critical" and "pay-07" in alerts[0]["message"]
