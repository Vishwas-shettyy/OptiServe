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


# ---- Section 14 acceptance tests (full pipeline) ----

KEYS = ["office_hours", "flash_sale", "forgotten_servers", "sick_server"]
_RESULTS: dict = {}


def _run(key: str, risk: float = 0.5):
    """Return a cached run_scenario result."""
    from engine.pipeline import run_scenario

    if (key, risk) not in _RESULTS:
        _RESULTS[(key, risk)] = run_scenario(key, risk)
    return _RESULTS[(key, risk)]


def _plan_cost(res) -> float:
    """Return total planned monthly cost across services."""
    return sum(sr.recommendation["planned_monthly"] for sr in res.services.values())


@pytest.mark.parametrize("key", KEYS)
def test_run_scenario_fast_and_deterministic(key: str) -> None:
    """run_scenario finishes in < 5 s and two runs give identical output."""
    import time

    from engine.pipeline import run_scenario

    t0 = time.perf_counter()
    a = run_scenario(key)
    assert time.perf_counter() - t0 < 5.0
    b = run_scenario(key)
    assert a.kpis == b.kpis and a.alerts == b.alerts
    pd.testing.assert_frame_equal(a.profile, b.profile)
    for name in a.services:
        sa, sb = a.services[name], b.services[name]
        pd.testing.assert_frame_equal(sa.forecast, sb.forecast)
        pd.testing.assert_frame_equal(sa.plan, sb.plan)
        assert sa.recommendation == sb.recommendation and sa.explanation == sb.explanation
        pd.testing.assert_frame_equal(sa.backtest["series"], sb.backtest["series"])


@pytest.mark.parametrize("key", KEYS)
def test_risk_cost_monotonic(key: str) -> None:
    """Plan cost at risk 0.0 is no more than at risk 1.0."""
    assert _plan_cost(_run(key, 0.0)) <= _plan_cost(_run(key, 1.0))


@pytest.mark.parametrize("key", KEYS)
def test_result_contract(key: str) -> None:
    """KPIs, backtest and explanation have the section 10–12 shape."""
    res = _run(key)
    assert set(res.kpis) == {"monthly_cost", "avg_util", "waste_score", "potential_savings", "zombies", "risky"}
    for sr in res.services.values():
        assert {"cost_fixed", "cost_plan", "savings_pct", "shortfall_hours_fixed", "shortfall_hours_plan",
                "overprov_hours_fixed", "overprov_hours_plan", "wape_optiserve", "wape_naive", "series"} == set(sr.backtest)
        assert list(sr.backtest["series"].columns) == ["timestamp", "actual", "capacity_fixed", "capacity_plan"]
        assert len(sr.backtest["series"]) == 168
        assert "₹" in sr.explanation and "Risk setting" in sr.explanation
    order = {"critical": 0, "warning": 1, "info": 2}
    assert [order[a["severity"]] for a in res.alerts] == sorted(order[a["severity"]] for a in res.alerts)


def test_acceptance_office_hours() -> None:
    """Night plan <= 3, backtest saves >= 30% with no shortfall, legacy Zombie, hr-portal mostly Wasteful."""
    res = _run("office_hours")
    sr = res.services["hr-portal"]
    ts = sr.plan["timestamp"].dt
    assert (sr.plan.loc[(ts.day_of_week < 5) & (ts.hour <= 5), "planned"] <= 3).all()
    assert sr.backtest["savings_pct"] >= 30
    assert sr.backtest["shortfall_hours_plan"] == 0
    p = res.profile
    assert (p.loc[p["service"] == "legacy", "status"] == "Zombie").all()
    assert (p.loc[p["service"] == "hr-portal", "status"] == "Wasteful").mean() > 0.5
    assert sr.backtest["wape_optiserve"] <= sr.backtest["wape_naive"] * 1.05
    assert "Balanced" in sr.explanation and "hr-portal: run" in sr.explanation


def test_acceptance_flash_sale() -> None:
    """Sale forecast x4, planned > 10 at 18:00, shortfall warning, backtest beats fixed."""
    res = _run("flash_sale")
    sr = res.services["shop-web"]
    high = sr.forecast.set_index("timestamp")["high"]
    assert high[pd.Timestamp("2026-11-20 20:00")] >= 4 * high[pd.Timestamp("2026-11-19 20:00")]
    assert sr.plan.set_index("timestamp").loc[pd.Timestamp("2026-11-20 18:00"), "planned"] > 10
    assert any(a["severity"] == "warning" and "Capacity shortfall expected" in a["message"] for a in res.alerts)
    assert sr.backtest["shortfall_hours_plan"] < sr.backtest["shortfall_hours_fixed"]


def test_acceptance_forgotten_servers() -> None:
    """Exactly 5 Zombies, waste score > 25, and an info alert about them."""
    res = _run("forgotten_servers")
    assert res.kpis["zombies"] == 5 and (res.profile["status"] == "Zombie").sum() == 5
    assert res.kpis["waste_score"] > 25
    assert any(a["severity"] == "info" and "5 zombie" in a["message"] for a in res.alerts)
    assert res.kpis["potential_savings"] >= 25000


def test_acceptance_sick_server() -> None:
    """pay-07 Risky, health blocked in plan and backtest, min planned >= 8, critical alert, spike anomaly."""
    res = _run("sick_server")
    sr = res.services["payments-api"]
    p = res.profile.set_index("server_id")
    assert p.loc["pay-07", "status"] == "Risky" and res.kpis["risky"] == 1
    health = next(g for g in sr.guardrails if g["rule"] == "Health")
    assert health["status"] == "blocked"
    assert sr.plan["planned"].min() >= 8
    assert res.alerts[0]["severity"] == "critical" and "pay-07" in res.alerts[0]["message"]
    spike = pd.Timestamp("2026-10-29 14:00")
    assert any(abs(a["timestamp"] - spike) <= pd.Timedelta(hours=2) for a in sr.anomalies)
    assert any(a["severity"] == "warning" and "Unusual traffic" in a["message"] for a in res.alerts)
    bt = sr.backtest
    assert (bt["series"]["capacity_plan"] >= bt["series"]["capacity_fixed"]).all()
    assert abs(bt["savings_pct"]) <= 1.0 and bt["shortfall_hours_plan"] == 0
    assert "payments-api: run 8 servers instead of a fixed 8." in sr.explanation


# ---- added scenarios: growth_startup and night_batch ---------------------------

def test_growth_startup_next_month_outlook() -> None:
    """growth_startup grows 5–11%/week, runs out of capacity within 6 weeks and needs more than 6 servers."""
    import math

    res = _run("growth_startup")
    rec = res.services["app-api"].recommendation
    assert 5 <= rec["growth_weekly_pct"] <= 11
    assert math.isfinite(rec["runway_weeks"]) and rec["runway_weeks"] < 6
    assert rec["month_servers"] > 6
    assert any(a["severity"] == "warning" and a["service"] == "app-api" and "Demand growing" in a["message"]
               for a in res.alerts)
    assert "for next month" in res.services["app-api"].explanation


def test_night_batch_plan_and_backtest() -> None:
    """night_batch runs >= 7 servers at 02:00 and <= 4 at 14:00, saves money and is never short in the backtest."""
    sr = _run("night_batch").services["reports-batch"]
    hours = sr.plan["timestamp"].dt.hour
    assert (sr.plan.loc[hours == 2, "planned"] >= 7).all()
    assert (sr.plan.loc[hours == 14, "planned"] <= 4).all()
    assert sr.backtest["savings_pct"] > 0 and sr.backtest["shortfall_hours_plan"] == 0
    assert sr.recommendation["month_servers"] is None


def test_new_scenarios_seeded_by_key() -> None:
    """The two added scenarios are listed, seeded from SEED + their key, and the original four keep index seeds."""
    from engine import config

    assert {"growth_startup", "night_batch"} <= {k for k, _ in list_scenarios()}
    assert data_gen.scenario_seed("office_hours") == config.SEED
    assert data_gen.scenario_seed("sick_server") == config.SEED + 3
    assert data_gen.scenario_seed("growth_startup") != data_gen.scenario_seed("night_batch")
    assert load_scenario("night_batch").current_servers == {"reports-batch": 8}
    assert load_scenario("growth_startup").current_servers == {"app-api": 6}


NEW_KEYS = ["growth_startup", "night_batch"]


@pytest.mark.parametrize("key", NEW_KEYS)
def test_new_scenarios_all_scenario_checks(key: str) -> None:
    """The existing all-scenario checks (speed, determinism, risk-cost order, result contract) hold for new keys."""
    test_run_scenario_fast_and_deterministic(key)
    test_risk_cost_monotonic(key)
    test_result_contract(key)
    test_forecast_shape_and_bands(key)
    for risk in (0.0, 1.0):
        test_guardrail_invariants(key, risk)
