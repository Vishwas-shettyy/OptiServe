"""Time Machine page: how the plan would have done on last week's real demand."""

import pandas as pd
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


def week_sparks(series: pd.DataFrame) -> dict[str, list[float]]:
    """Return daily sparklines for the test week: capacity freed, hours short, idle share % and demand."""
    s = series.assign(freed=series["capacity_fixed"] - series["capacity_plan"],
                      short=(series["actual"] > series["capacity_plan"]).astype(int),
                      idle=((series["capacity_plan"] - series["actual"]).clip(lower=0)
                            / series["capacity_plan"].where(series["capacity_plan"] > 0) * 100).fillna(0))
    return {"saved": charts.daily(s, "freed"), "short": charts.daily(s, "short"),
            "idle": charts.daily(s, "idle", "mean"), "demand": charts.daily(s, "actual")}


def _vs_fixed(plan: int, fixed: int) -> dict:
    """Return delta fields comparing an hour count with the fixed setup (fewer is better)."""
    diff = plan - fixed
    text = "Same as fixed setup" if diff == 0 else f"{abs(diff)} {'fewer' if diff < 0 else 'more'} than fixed ({fixed})"
    return dict(delta=text, delta_up=diff > 0, delta_good=diff <= 0)


def render_service(sr: ServiceResult) -> None:
    """Draw the backtest for one service."""
    bt = sr.backtest
    components.insight_banner(*insight(sr))
    saved = bt["cost_fixed"] - bt["cost_plan"]
    ours, naive = bt["wape_optiserve"] * 100, bt["wape_naive"] * 100
    sparks = week_sparks(bt["series"])
    short_p, short_f = bt["shortfall_hours_plan"], bt["shortfall_hours_fixed"]
    components.kpi_row([
        dict(label="Saved in test week", value=money_short(saved), tooltip=money(saved), icon_name="wallet",
             tone="success" if saved > 0 else "neutral", spark=sparks["saved"],
             delta=f"{abs(bt['savings_pct']):.1f}% vs fixed setup", delta_up=saved < 0, delta_good=saved >= 0),
        dict(label="Hours short of capacity", value=str(short_p), icon_name="alert-triangle", spark=sparks["short"],
             tone="danger" if short_p > short_f else "success", **_vs_fixed(short_p, short_f)),
        dict(label="Hours with idle capacity", value=str(bt["overprov_hours_plan"]), icon_name="moon", tone="info",
             spark=sparks["idle"], **_vs_fixed(bt["overprov_hours_plan"], bt["overprov_hours_fixed"])),
        dict(label="Forecast error", value=f"{ours:.1f}%", icon_name="target", spark=sparks["demand"],
             tone="success" if ours <= naive else "warning",
             delta=f"{abs(naive - ours):.1f} pts {'better' if ours <= naive else 'worse'} than simple",
             delta_up=ours > naive, delta_good=ours <= naive),
    ])
    components.before_after([
        ("Cost of the week", bt["cost_fixed"], bt["cost_plan"], "money"),
        ("Hours short of capacity", bt["shortfall_hours_fixed"], bt["shortfall_hours_plan"], "hours"),
        ("Hours with idle capacity", bt["overprov_hours_fixed"], bt["overprov_hours_plan"], "hours"),
    ])
    left, right = st.columns([2, 1], gap="medium")
    with left:
        with st.container(border=True, key=f"card_week_{sr.service}"):
            components.card_title("Replayed test week", "Real demand against both setups; red hours ran short of "
                                  "capacity.", "history")
            st.plotly_chart(charts.test_week_chart(bt["series"]), width="stretch", theme=None, key=f"tm_{sr.service}",
                            config={"scrollZoom": False, "displayModeBar": False})
    with right:
        better = "more" if ours <= naive else "less"
        with st.container(border=True, key=f"card_acc_{sr.service}"):
            components.card_title("Forecast accuracy", "Average error per hour; lower is better.", "target")
            components.compare_bars(f"OptiServe {ours:.1f}% vs simple method {naive:.1f}%", [
                ("OptiServe", ours, charts.EXPECTED_COLOR),
                ("Simple method (same hour last week)", naive, charts.CURRENT_COLOR),
            ], f"OptiServe is {abs(naive - ours):.1f} points {better} accurate.")


def render(result: ScenarioResult) -> None:
    """Draw the Time Machine page."""
    components.page_header("Time Machine", "Trained on the first three weeks, then replayed the last one: what if "
                                           "OptiServe had run the fleet?", icon_name="history")
    services = [s for s, sr in result.services.items() if sr.backtest]
    if not services:
        components.text_card("Nothing to replay", "This scenario has no active services to backtest.")
        return
    for tab, name in zip(st.tabs(services), services):
        with tab:
            render_service(result.services[name])
