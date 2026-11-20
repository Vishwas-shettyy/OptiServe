"""Forecast & Plan page: demand forecast, hourly server plan, recommendation and safety checks."""

import pandas as pd
import streamlit as st

from engine import config
from engine.pipeline import ScenarioResult, ServiceResult
from ui import charts, components
from ui.components import money, money_short

SPARK_DAYS = 14


def insight(sr: ServiceResult) -> tuple[str, str]:
    """Return (sentence, tone) with the page's key number for one service."""
    rec = sr.recommendation
    blocked = [g for g in sr.guardrails if g["status"] == "blocked"]
    rng = components.server_range(rec["planned_min"], rec["planned_max"])
    if blocked and rec["savings_monthly"] <= 0:
        return f"Scale-down held back on {sr.service}: {blocked[0]['message']}", "warning"
    if rec["action"] == "scale_up":
        return (f"{sr.service} needs up to {rec['planned_max']} servers at its busiest hour "
                f"({rec['peak_time']:%a %d %b %H:%M}); you run {rec['current']} today.", "warning")
    if rec["savings_monthly"] > 0:
        return (f"Run {rng} servers instead of a fixed {rec['current']} on {sr.service} and save "
                f"{money(rec['savings_monthly'])}/month ({rec['savings_pct']:.0f}%).", "success")
    return f"{sr.service} is right-sized: keep {rec['current']} servers.", "info"


def kpi_sparks(sr: ServiceResult, cost: float) -> dict[str, list[float]]:
    """Return daily sparkline series: recent demand, planned servers, saving per day and safety headroom."""
    hist = sr.history[sr.history["timestamp"] > sr.history["timestamp"].max() - pd.Timedelta(days=SPARK_DAYS)]
    plan = sr.plan.assign(saved=(sr.plan["current"] - sr.plan["planned"]) * cost / config.HOURS_PER_MONTH,
                          headroom=sr.plan["planned"] - sr.plan["needed_raw"])
    return {"demand": charts.daily(hist, "requests"), "planned": charts.daily(plan, "planned", "mean"),
            "saving": charts.daily(plan, "saved"), "headroom": charts.daily(plan, "headroom", "mean")}


def render_kpis(sr: ServiceResult, cost: float) -> None:
    """Draw current servers, planned range, saving and safety checks passed, with icons, deltas and sparklines."""
    rec, sparks = sr.recommendation, kpi_sparks(sr, cost)
    passed = sum(g["status"] == "pass" for g in sr.guardrails)
    total = len(sr.guardrails)
    n_blocked = sum(g["status"] == "blocked" for g in sr.guardrails)
    n_adjusted = sum(g["status"] == "adjusted" for g in sr.guardrails)
    savings = rec["savings_monthly"]
    spare = rec["current"] - rec["planned_max"]
    components.kpi_row([
        dict(label="Current servers", value=str(rec["current"]), tone="info", icon_name="server",
             spark=sparks["demand"], delta=f"{abs(spare)} {'spare' if spare >= 0 else 'short'} at the busiest hour",
             delta_up=spare < 0, delta_good=spare >= 0),
        dict(label="Planned range", value=components.server_range(rec["planned_min"], rec["planned_max"]),
             tone="info", icon_name="layers", spark=sparks["planned"],
             delta=f"Avg {rec['planned_avg']:.1f} per hour vs {rec['current']}",
             delta_up=rec["planned_avg"] > rec["current"], delta_good=rec["planned_avg"] <= rec["current"] or None),
        dict(label="Saving / month" if savings >= 0 else "Extra cost / month", value=money_short(abs(savings)),
             tooltip=money(abs(savings)), icon_name="wallet", spark=sparks["saving"],
             tone="success" if savings > 0 else ("warning" if savings < 0 else "neutral"),
             delta=f"{abs(rec['savings_pct']):.0f}% of {money_short(rec['current_monthly'])} today",
             delta_up=savings < 0, delta_good=savings >= 0 or None),
        dict(label="Safety checks", value=f"{passed}/{total}", icon_name="shield-check", spark=sparks["headroom"],
             tone="danger" if n_blocked else ("warning" if n_adjusted else "success"),
             delta=f"{n_blocked} blocked · {n_adjusted} adjusted", delta_up=passed == total,
             delta_good=True if passed == total else (False if n_blocked else None)),
    ])


def render(result: ScenarioResult) -> None:
    """Draw the Forecast & Plan page."""
    sc = result.scenario
    services = [name for name, sr in result.services.items() if not sr.plan.empty]
    head, pick = st.columns([3, 1], vertical_alignment="bottom")
    with head:
        components.page_header("Forecast & Plan", f"Next {config.FORECAST_HOURS // 24} days of demand and the "
                               f"hour-by-hour server plan · {config.risk_label(result.risk)} mode", icon_name="chart-line")
    if not services:
        components.text_card("Nothing to plan", "This scenario has no active services with a forecast.")
        return
    name = services[0]
    if len(services) > 1:
        name = pick.selectbox("Service", services)
    sr = result.services[name]
    servers = sc.servers
    capacity_rps = float(servers.loc[servers["service"] == name, "capacity_rps"].mean())
    cost = float(servers.loc[servers["service"] == name, "monthly_cost"].mean())
    components.insight_banner(*insight(sr))
    render_kpis(sr, cost)
    hist = sr.history[sr.history["timestamp"] > sr.history["timestamp"].max() - pd.Timedelta(days=7)]
    left, right = st.columns([2, 1], gap="medium")
    with left:
        with st.container(border=True, key="card_demand"):
            components.card_title("Demand vs capacity", "Last 7 days of actual requests, then the forecast with its "
                                  "likely range, against current and planned capacity.", "chart-line")
            st.plotly_chart(charts.demand_chart(hist, sr.forecast, sr.plan, sc.events[sc.events["service"] == name],
                                                capacity_rps), width="stretch", theme=None,
                            config={"scrollZoom": False, "displayModeBar": False})
        with st.container(border=True, key="card_servers"):
            components.card_title("Servers per hour", "The plan adds servers before busy hours and removes them "
                                  "when quiet.", "server")
            st.plotly_chart(charts.servers_chart(sr.plan), width="stretch", theme=None,
                            config={"scrollZoom": False, "displayModeBar": False})
    with right:
        with st.container(border=True, key="card_rec"):
            components.card_title("Recommendation", "What to run next week.", "sparkles")
            rec = sr.recommendation
            components.recommendation_card(name, str(rec["action"]), rec["current"], rec["planned_min"],
                                           rec["planned_max"], rec["savings_monthly"], rec["savings_pct"])
            with st.expander("Why this plan?", expanded=False):
                st.write(sr.explanation)
        with st.container(border=True, key="card_checks"):
            components.card_title("Safety checks", f"{passed_text(sr)} before the plan is used.", "shield-check")
            components.checklist("", sr.guardrails)


def passed_text(sr: ServiceResult) -> str:
    """Return 'N of M passed' for a service's safety checks."""
    return f"{sum(g['status'] == 'pass' for g in sr.guardrails)} of {len(sr.guardrails)} passed"
