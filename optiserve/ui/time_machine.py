"""Time Machine page: how the plan would have done on last week's real demand."""

import streamlit as st

from engine.pipeline import ScenarioResult, ServiceResult
from ui import charts, components
from ui.components import money, money_short

HELD_BACK = "Savings held back: a server is unhealthy, so OptiServe keeps capacity. Reliability first."


def insight(sr: ServiceResult) -> tuple[str, str]:
    """Return (sentence, tone) summarising the replayed week."""
    bt = sr.backtest
    blocked = any(g["status"] == "blocked" for g in sr.guardrails)
    if blocked and abs(bt["savings_pct"]) < 1e-9:
        return HELD_BACK, "info"
    saved = bt["cost_fixed"] - bt["cost_plan"]
    short_p, short_f = bt["shortfall_hours_plan"], bt["shortfall_hours_fixed"]
    if saved > 0:
        return (f"Last week OptiServe would have saved {money(saved)} ({bt['savings_pct']:.0f}%) with "
                f"{short_p} hours short of capacity (fixed setup: {short_f}).", "success" if short_p <= short_f else "warning")
    if short_p < short_f:
        return (f"OptiServe would have spent {money(-saved)} more last week but cut hours short of capacity "
                f"from {short_f} to {short_p}.", "info")
    return "Last week OptiServe would have matched the fixed setup.", "neutral"


def render_service(sr: ServiceResult) -> None:
    """Draw the backtest for one service."""
    bt = sr.backtest
    components.insight_banner(*insight(sr))
    saved = bt["cost_fixed"] - bt["cost_plan"]
    ours, naive = bt["wape_optiserve"] * 100, bt["wape_naive"] * 100
    components.kpi_row([
        dict(label="Saved in test week", value=money_short(saved), hint=f"{bt['savings_pct']:.1f}% vs fixed setup",
             tone="success" if saved > 0 else "neutral", tooltip=money(saved)),
        dict(label="Hours short of capacity", value=str(bt["shortfall_hours_plan"]),
             hint=f"Fixed setup: {bt['shortfall_hours_fixed']}",
             tone="danger" if bt["shortfall_hours_plan"] > bt["shortfall_hours_fixed"] else "success"),
        dict(label="Hours with idle capacity", value=str(bt["overprov_hours_plan"]),
             hint=f"Fixed setup: {bt['overprov_hours_fixed']}"),
        dict(label="Forecast error", value=f"{ours:.1f}%", hint=f"Simple method: {naive:.1f}%",
             tone="success" if ours <= naive else "warning"),
    ])
    components.before_after([
        ("Cost of the week", bt["cost_fixed"], bt["cost_plan"], "money"),
        ("Hours short of capacity", bt["shortfall_hours_fixed"], bt["shortfall_hours_plan"], "hours"),
        ("Hours with idle capacity", bt["overprov_hours_fixed"], bt["overprov_hours_plan"], "hours"),
    ])
    left, right = st.columns([2, 1], gap="large")
    with left:
        components.section("Replayed test week", "Real demand against both setups; red hours ran short of capacity.")
        st.plotly_chart(charts.test_week_chart(bt["series"]), width="stretch", theme=None, key=f"tm_{sr.service}")
    with right:
        components.section("Forecast accuracy", "Average error per hour; lower is better.")
        better = "more" if ours <= naive else "less"
        components.compare_bars(f"OptiServe {ours:.1f}% vs simple method {naive:.1f}%", [
            ("OptiServe", ours, charts.EXPECTED_COLOR),
            ("Simple method (same hour last week)", naive, charts.CURRENT_COLOR),
        ], f"OptiServe is {abs(naive - ours):.1f} points {better} accurate.")


def render(result: ScenarioResult) -> None:
    """Draw the Time Machine page."""
    components.page_header("Time Machine", "Trained on the first three weeks, then replayed the last one: what if "
                                           "OptiServe had run the fleet?", result.scenario.title)
    services = [s for s, sr in result.services.items() if sr.backtest]
    if not services:
        components.text_card("Nothing to replay", "This scenario has no active services to backtest.")
        return
    for tab, name in zip(st.tabs(services), services):
        with tab:
            render_service(result.services[name])
