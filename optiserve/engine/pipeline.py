"""Glue: run a full scenario end to end."""

import time
from dataclasses import dataclass, field

import pandas as pd

from engine import backtest, config, data_gen, explainer, forecaster, guardrails, planner, profiler
from engine.data_gen import Scenario


@dataclass
class ServiceResult:
    """All outputs for one service."""

    service: str
    history: pd.DataFrame
    forecast: pd.DataFrame
    plan: pd.DataFrame
    guardrails: list[dict] = field(default_factory=list)
    recommendation: dict = field(default_factory=dict)
    explanation: str = ""
    backtest: dict = field(default_factory=dict)
    anomalies: list[dict] = field(default_factory=list)


@dataclass
class ScenarioResult:
    """All outputs for one scenario run."""

    scenario: Scenario
    risk: float
    profile: pd.DataFrame
    services: dict[str, ServiceResult] = field(default_factory=dict)
    alerts: list[dict] = field(default_factory=list)
    kpis: dict = field(default_factory=dict)


def _service_result(
    sc: Scenario, service: str, demand: pd.DataFrame, profile: pd.DataFrame, risk: float
) -> ServiceResult:
    """Run forecast, plan, guardrails, recommendation, explanation and backtest for one service."""
    params = config.risk_params(risk)
    history = demand[demand["service"] == service].reset_index(drop=True)
    srv = sc.servers[sc.servers["service"] == service]
    monthly_cost = float(srv["monthly_cost"].mean())
    capacity = float(srv["capacity_rps"].mean())
    current = int(sc.current_servers[service])
    start = history["timestamp"].max() + pd.Timedelta(hours=1)
    fc, anomalies = forecaster.forecast_service(history, sc.events, start, config.FORECAST_HOURS, params["z"])
    raw = planner.build_plan(fc, current, capacity, params["target_util"])
    span = history["timestamp"].max() - history["timestamp"].min()
    history_days = int(round(span / pd.Timedelta(days=1))) + 1
    prof = profile[profile["service"] == service]
    plan, rules = guardrails.apply_guardrails(raw, fc, prof, history_days, current)
    rec = planner.recommend(plan, monthly_cost, current)
    return ServiceResult(
        service=service,
        history=history,
        forecast=fc,
        plan=plan,
        guardrails=rules,
        recommendation=rec,
        explanation=explainer.explain(service, rec, rules, risk),
        backtest=backtest.run_backtest(history, sc.events, current, capacity, monthly_cost, risk, prof),
        anomalies=anomalies,
    )


def _kpis(sc: Scenario, profile: pd.DataFrame, services: dict[str, ServiceResult]) -> dict:
    """Compute headline KPIs for a scenario."""
    active = profile[profile["service"] != data_gen.ZOMBIE_SERVICE]["server_id"]
    end = sc.metrics["timestamp"].max()
    recent = sc.metrics[(sc.metrics["timestamp"] > end - pd.Timedelta(days=config.ZOMBIE_DAYS))
                        & sc.metrics["server_id"].isin(active)]
    zombies = profile[profile["status"] == "Zombie"]
    service_savings = sum(max(r.recommendation["savings_monthly"], 0.0) for r in services.values())
    return {
        "monthly_cost": float(profile["monthly_cost"].sum()),
        "avg_util": round(float(recent["cpu_pct"].mean()), 2),
        "waste_score": profiler.waste_score(profile),
        "potential_savings": round(float(zombies["monthly_cost"].sum()) + service_savings, 2),
        "zombies": int(len(zombies)),
        "risky": int((profile["status"] == "Risky").sum()),
    }


def run_scenario(key: str, risk: float = config.DEFAULT_RISK) -> ScenarioResult:
    """Run the full pipeline for one scenario."""
    risk = min(max(float(risk), 0.0), 1.0)
    sc = data_gen.load_scenario(key)
    profile = profiler.profile_servers(sc.metrics, sc.servers)
    demand = forecaster.service_demand(sc.metrics, sc.servers)
    services = {
        service: _service_result(sc, service, demand, profile, risk)
        for service, count in sc.current_servers.items()
        if count > 0
    }
    alerts = guardrails.build_alerts(profile, services)
    return ScenarioResult(sc, risk, profile, services, alerts, _kpis(sc, profile, services))


def _money(value: float) -> str:
    """Format a rupee amount with thousand separators."""
    return f"{config.CURRENCY}{value:,.0f}"


def main() -> None:
    """Print one summary block per scenario."""
    for key, title in data_gen.list_scenarios():
        t0 = time.perf_counter()
        res = run_scenario(key)
        elapsed = time.perf_counter() - t0
        k = res.kpis
        print(f"=== {title} [{key}] ({elapsed:.2f}s, risk {res.risk:.2f} {config.risk_label(res.risk)}) ===")
        print(f"  Monthly cost {_money(k['monthly_cost'])} | avg util {k['avg_util']:.1f}% | waste score "
              f"{k['waste_score']:.1f}% | potential savings {_money(k['potential_savings'])} | "
              f"zombies {k['zombies']} | risky {k['risky']}")
        for name, sr in res.services.items():
            rec, bt = sr.recommendation, sr.backtest
            print(f"  [{name}] action {rec['action']}: {rec['planned_min']}-{rec['planned_max']} servers "
                  f"(avg {rec['planned_avg']:.1f}) vs fixed {rec['current']}, saves {_money(rec['savings_monthly'])}"
                  f"/month ({rec['savings_pct']:.1f}%)")
            blocked = [g["rule"] for g in sr.guardrails if g["status"] == "blocked"]
            print(f"    Blocked rules: {', '.join(blocked) if blocked else 'none'} | anomalies {len(sr.anomalies)}")
            print(f"    Backtest: cost fixed {_money(bt['cost_fixed'])} vs plan {_money(bt['cost_plan'])} "
                  f"({bt['savings_pct']:.1f}% saved) | shortfall h fixed {bt['shortfall_hours_fixed']} / plan "
                  f"{bt['shortfall_hours_plan']} | overprov h fixed {bt['overprov_hours_fixed']} / plan "
                  f"{bt['overprov_hours_plan']} | WAPE {bt['wape_optiserve']:.3f} vs naive {bt['wape_naive']:.3f}")
            print(f"    {sr.explanation}")
        for a in res.alerts:
            print(f"  ({a['severity']}) {a['service']}: {a['message']}")
        print()


if __name__ == "__main__":
    main()
