"""Overview page: insight, KPIs, fleet status, recommendations and alerts."""

import streamlit as st

from engine.pipeline import ScenarioResult
from ui import charts, components
from ui.components import money, money_short  # noqa: F401  (re-exported for other pages)


def insight(result: ScenarioResult) -> tuple[str, str]:
    """Return (sentence, tone): the first critical alert, else the biggest saving."""
    critical = [a for a in result.alerts if a["severity"] == "critical"]
    if critical:
        a = critical[0]
        more = f" (+{len(critical) - 1} more critical)" if len(critical) > 1 else ""
        return f"{a['service']}: {a['message']}{more}", "danger"
    best = max(result.services.values(), key=lambda sr: sr.recommendation["savings_monthly"], default=None)
    if best is not None and best.recommendation["savings_monthly"] > 0:
        rec = best.recommendation
        short = best.backtest.get("shortfall_hours_plan") if best.backtest else None
        tail = f", with {short} hours short of capacity in last week's replay" if short is not None else ""
        return (f"OptiServe can save {money(rec['savings_monthly'])}/month on {best.service} "
                f"({rec['savings_pct']:.0f}%){tail}.", "success")
    zombies = result.kpis.get("zombies", 0)
    if zombies:
        return f"{zombies} idle server(s) can be switched off to cut waste.", "warning"
    return "Your fleet is already right-sized: no savings or alerts right now.", "info"


def render_kpis(result: ScenarioResult) -> None:
    """Draw the four headline KPI cards."""
    k = result.kpis
    components.kpi_row([
        dict(label="Monthly cost", value=money_short(k["monthly_cost"]), hint="All servers today",
             tooltip=money(k["monthly_cost"])),
        dict(label="Avg CPU", value=f"{k['avg_util']:.1f}%", hint="Active servers, last 14 days"),
        dict(label="Waste score", value=f"{k['waste_score']:.1f}%",
             hint=f"{k['zombies']} idle · {k['risky']} unhealthy",
             tone="warning" if k["waste_score"] > 25 else "neutral"),
        dict(label="Potential savings", value=money_short(k["potential_savings"]), hint="Per month, idle + right-sizing",
             tone="success" if k["potential_savings"] > 0 else "neutral", tooltip=money(k["potential_savings"])),
    ])


def render_recommendations(result: ScenarioResult) -> None:
    """Draw one recommendation card per service."""
    components.section("Recommendations", "What to change for each service, and what it saves.")
    if not result.services:
        components.text_card("Nothing to plan", "This scenario has no active services.")
        return
    for name, sr in result.services.items():
        rec = sr.recommendation
        components.recommendation_card(name, str(rec["action"]), rec["current"], rec["planned_min"],
                                       rec["planned_max"], rec["savings_monthly"], rec["savings_pct"], sr.explanation)


def render(result: ScenarioResult) -> None:
    """Draw the overview page."""
    sc = result.scenario
    components.page_header("Overview", sc.story, sc.title)
    components.insight_banner(*insight(result))
    render_kpis(result)
    left, right = st.columns([2, 1], gap="large")
    with left:
        components.section("Fleet status", "Every server, grouped by how well it is sized.")
        counts = result.profile["status"].value_counts().to_dict()
        st.plotly_chart(charts.fleet_status_bar(counts), width="stretch", config={"displayModeBar": False})
        render_recommendations(result)
    with right:
        components.section(f"Alerts ({len(result.alerts)})", "Most urgent first.")
        components.alerts_feed(result.alerts)
