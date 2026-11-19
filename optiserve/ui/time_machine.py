"""Time Machine page: how the plan would have done on last week's real demand."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.pipeline import ScenarioResult
from ui.forecast_plan import ACTUAL_COLOR, CURRENT_COLOR, PLANNED_COLOR, _layout
from ui.overview import money
from ui.styles import ACCENT

SHORT_COLOR = "#ef4444"


def tile(label: str, fixed: str, plan: str) -> str:
    """Return HTML for a fixed-vs-OptiServe comparison tile."""
    return (f'<div class="os-tile"><div class="label">{label}</div>'
            f'<div class="row"><span>Fixed</span><b>{fixed}</b></div>'
            f'<div class="row"><span>OptiServe</span><b style="color:{PLANNED_COLOR}">{plan}</b></div></div>')


def render_tiles(bt: dict) -> None:
    """Draw the cost, savings, shortfall and over-provisioning tiles."""
    cols = st.columns(4)
    cols[0].markdown(tile("Cost of test week", money(bt["cost_fixed"]), money(bt["cost_plan"])), unsafe_allow_html=True)
    color = PLANNED_COLOR if bt["savings_pct"] >= 0 else SHORT_COLOR
    cols[1].markdown(f'<div class="os-tile"><div class="label">Savings</div>'
                     f'<div class="big" style="color:{color}">{bt["savings_pct"]:.1f}%</div></div>',
                     unsafe_allow_html=True)
    cols[2].markdown(tile("Shortfall hours", str(bt["shortfall_hours_fixed"]), str(bt["shortfall_hours_plan"])),
                     unsafe_allow_html=True)
    cols[3].markdown(tile("Over-provisioned hours", str(bt["overprov_hours_fixed"]), str(bt["overprov_hours_plan"])),
                     unsafe_allow_html=True)


def test_week_chart(series: pd.DataFrame) -> go.Figure:
    """Return the test-week chart with shortfall hours marked in red."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series["timestamp"], y=series["capacity_fixed"], name="Fixed capacity",
                             line=dict(color=CURRENT_COLOR, dash="dash", shape="hv")))
    fig.add_trace(go.Scatter(x=series["timestamp"], y=series["capacity_plan"], name="OptiServe capacity",
                             line=dict(color=PLANNED_COLOR, width=2, shape="hv")))
    fig.add_trace(go.Scatter(x=series["timestamp"], y=series["actual"], name="Actual demand",
                             line=dict(color=ACTUAL_COLOR, width=1.6)))
    for col, name, symbol in (("capacity_fixed", "Shortfall (fixed)", "x"), ("capacity_plan", "Shortfall (OptiServe)", "circle")):
        short = series[series["actual"] > series[col]]
        if not short.empty:
            fig.add_trace(go.Scatter(x=short["timestamp"], y=short["actual"], mode="markers", name=name,
                                     marker=dict(color=SHORT_COLOR, size=8, symbol=symbol)))
    for ts in series.loc[series["actual"] > series["capacity_plan"], "timestamp"]:
        fig.add_vrect(x0=ts, x1=ts + pd.Timedelta(hours=1), fillcolor=SHORT_COLOR, opacity=0.18,
                      line_width=0, layer="below")
    return _layout(fig, 420, "Requests / sec")


def wape_card(bt: dict) -> str:
    """Return HTML comparing OptiServe and naive forecast error (WAPE)."""
    ours, naive = bt["wape_optiserve"] * 100, bt["wape_naive"] * 100
    width = max(ours, naive, 1e-9)

    def bar(v: float, c: str) -> str:
        """Return a horizontal bar sized relative to the larger WAPE."""
        return (f'<div style="background:#1f2937;border-radius:6px;height:8px;margin:.2rem 0 .5rem">'
                f'<div style="width:{v / width * 100:.0f}%;background:{c};height:8px;border-radius:6px"></div></div>')

    verdict = "more accurate" if ours <= naive else "less accurate"
    return (f'<div class="os-card"><h4>Forecast accuracy: OptiServe vs naive</h4>'
            f'<p>WAPE (lower is better)</p>'
            f'<p>OptiServe <b>{ours:.1f}%</b></p>{bar(ours, ACCENT)}'
            f'<p>Naive (same hour last week) <b>{naive:.1f}%</b></p>{bar(naive, CURRENT_COLOR)}'
            f'<p style="color:#94a3b8;font-size:.85rem">OptiServe is {abs(naive - ours):.1f} pts {verdict}.</p></div>')


def render(result: ScenarioResult) -> None:
    """Draw the Time Machine page."""
    st.title("Time Machine")
    st.markdown('<div class="os-story">We trained on the first three weeks, then replayed the last week: '
                'what if OptiServe had been running the fleet?</div>', unsafe_allow_html=True)
    services = [s for s, sr in result.services.items() if sr.backtest]
    if not services:
        st.info("No services to backtest in this scenario.")
        return
    for tab, name in zip(st.tabs(services), services):
        bt = result.services[name].backtest
        with tab:
            render_tiles(bt)
            left, right = st.columns([3, 1.1])
            left.plotly_chart(test_week_chart(bt["series"]), width="stretch", key=f"tm_{name}")
            right.markdown(wape_card(bt), unsafe_allow_html=True)
