"""Forecast & Plan page: demand forecast, hourly server plan, recommendation and safety checks."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import config
from engine.pipeline import ScenarioResult, ServiceResult
from ui import charts, components
from ui.charts import ACTUAL_COLOR, CURRENT_COLOR, PLANNED_COLOR  # noqa: F401  (used by time_machine)
from ui.components import money, money_short


def _layout(fig: go.Figure, height: int, y_title: str) -> go.Figure:
    """Apply the shared chart style (kept for pages that still import it)."""
    return charts.layout(fig, height, y_title)


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


def render_kpis(sr: ServiceResult) -> None:
    """Draw current servers, planned range, saving and safety checks passed."""
    rec = sr.recommendation
    passed = sum(g["status"] == "pass" for g in sr.guardrails)
    total = len(sr.guardrails)
    n_blocked = sum(g["status"] == "blocked" for g in sr.guardrails)
    n_adjusted = sum(g["status"] == "adjusted" for g in sr.guardrails)
    savings = rec["savings_monthly"]
    components.kpi_row([
        dict(label="Current servers", value=str(rec["current"]), hint="Fixed, every hour"),
        dict(label="Planned range", value=components.server_range(rec["planned_min"], rec["planned_max"]),
             hint=f"Avg {rec['planned_avg']:.1f} per hour", tone="info"),
        dict(label="Saving / month" if savings >= 0 else "Extra cost / month",
             value=money_short(abs(savings)), hint=f"{abs(rec['savings_pct']):.1f}% vs {money(rec['current_monthly'])}",
             tone="success" if savings > 0 else ("warning" if savings < 0 else "neutral"), tooltip=money(abs(savings))),
        dict(label="Safety checks passed", value=f"{passed}/{total}",
             hint=f"{n_blocked} blocked · {n_adjusted} adjusted",
             tone="danger" if n_blocked else ("warning" if n_adjusted else "success")),
    ])


def render(result: ScenarioResult) -> None:
    """Draw the Forecast & Plan page."""
    sc = result.scenario
    components.page_header("Forecast & Plan",
                           f"Next {config.FORECAST_HOURS // 24} days of demand and the hour-by-hour server plan · "
                           f"{config.risk_label(result.risk)} mode", sc.title)
    services = [name for name, sr in result.services.items() if not sr.plan.empty]
    if not services:
        components.text_card("Nothing to plan", "This scenario has no active services with a forecast.")
        return
    name = services[0]
    if len(services) > 1:
        name = st.columns([1, 3])[0].selectbox("Service", services)
    sr = result.services[name]
    components.insight_banner(*insight(sr))
    render_kpis(sr)
    servers = sc.servers
    capacity_rps = float(servers.loc[servers["service"] == name, "capacity_rps"].mean())
    hist = sr.history[sr.history["timestamp"] > sr.history["timestamp"].max() - pd.Timedelta(days=7)]
    left, right = st.columns([2, 1], gap="large")
    with left:
        components.section("Demand vs capacity", "Last 7 days of actual requests, then the forecast with its "
                                                 "likely range, against current and planned capacity.")
        st.plotly_chart(charts.demand_chart(hist, sr.forecast, sr.plan, sc.events[sc.events["service"] == name],
                                            capacity_rps), width="stretch")
        components.section("Servers per hour", "The plan adds servers before busy hours and removes them when quiet.")
        st.plotly_chart(charts.servers_chart(sr.plan), width="stretch")
    with right:
        components.section("Recommendation")
        rec = sr.recommendation
        components.recommendation_card(name, str(rec["action"]), rec["current"], rec["planned_min"],
                                       rec["planned_max"], rec["savings_monthly"], rec["savings_pct"])
        components.text_card("Why", sr.explanation)
        components.checklist("Safety checks", sr.guardrails)
