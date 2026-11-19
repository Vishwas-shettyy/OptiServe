"""Forecast & Plan page: demand forecast, server plan, recommendation and guardrails."""

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import config
from engine.pipeline import ScenarioResult, ServiceResult
from ui.overview import ACTION_COLORS, money
from ui.styles import ACCENT, chip

RULE_ICONS = {"pass": "✅", "adjusted": "🟡", "blocked": "⛔"}
ACTUAL_COLOR = "#e2e8f0"
CURRENT_COLOR = "#94a3b8"
PLANNED_COLOR = "#22c55e"
EVENT_FILL = "rgba(251,146,60,0.15)"


def _layout(fig: go.Figure, height: int, y_title: str) -> go.Figure:
    """Apply the shared dark, transparent layout."""
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=height, margin=dict(l=10, r=10, t=30, b=10), yaxis_title=y_title,
                      hovermode="x unified", legend=dict(orientation="h", y=1.08, x=0))
    return fig


def _shade_events(fig: go.Figure, events: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> None:
    """Shade and label event windows that overlap the visible range."""
    for ev in events.itertuples():
        if ev.end < start or ev.start > end:
            continue
        x0, x1 = max(ev.start, start), min(ev.end + pd.Timedelta(hours=1), end)
        fig.add_vrect(x0=x0, x1=x1, fillcolor=EVENT_FILL, line_width=0, layer="below",
                      annotation_text=ev.label, annotation_position="top left",
                      annotation_font_color="#fb923c", annotation_font_size=11)


def demand_chart(sr: ServiceResult, capacity_rps: float, events: pd.DataFrame) -> go.Figure:
    """Build the requests chart: actuals, forecast band, current and planned capacity."""
    hist = sr.history[sr.history["timestamp"] > sr.history["timestamp"].max() - pd.Timedelta(days=7)]
    fc, plan = sr.forecast, sr.plan
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fc["timestamp"], y=fc["high"], line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=fc["timestamp"], y=fc["low"], line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(56,189,248,0.18)", name="Forecast range (low–high)",
                             hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=hist["timestamp"], y=hist["requests"], name="Actual requests",
                             line=dict(color=ACTUAL_COLOR, width=1.6), hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=fc["timestamp"], y=fc["expected"], name="Forecast (expected)",
                             line=dict(color=ACCENT, width=2), hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=plan["timestamp"], y=plan["current"] * capacity_rps, name="Current capacity",
                             line=dict(color=CURRENT_COLOR, dash="dash", shape="hv"), hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=plan["timestamp"], y=plan["planned"] * capacity_rps, name="Planned capacity",
                             line=dict(color=PLANNED_COLOR, width=2, shape="hv"), hovertemplate="%{y:,.0f}"))
    start = hist["timestamp"].min()
    end = fc["timestamp"].max() + pd.Timedelta(hours=1)
    _shade_events(fig, events[events["service"] == sr.service], start, end)
    fig.add_vline(x=fc["timestamp"].min(), line=dict(color="#475569", dash="dot", width=1))
    return _layout(fig, 420, "Requests per hour")


def servers_chart(sr: ServiceResult) -> go.Figure:
    """Build the servers-per-hour chart: current vs planned."""
    plan = sr.plan
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=plan["timestamp"], y=plan["current"], name="Current servers",
                             line=dict(color=CURRENT_COLOR, dash="dash", shape="hv")))
    fig.add_trace(go.Scatter(x=plan["timestamp"], y=plan["planned"], name="Planned servers",
                             line=dict(color=PLANNED_COLOR, width=2, shape="hv"),
                             fill="tozeroy", fillcolor="rgba(34,197,94,0.10)"))
    fig.update_yaxes(rangemode="tozero")
    return _layout(fig, 280, "Servers")


def recommendation_card(sr: ServiceResult) -> str:
    """Return HTML for the recommendation card."""
    rec = sr.recommendation
    action = str(rec["action"])
    badge = chip(html.escape(action.replace("_", " ").capitalize()), ACTION_COLORS.get(action, "#f59e0b"))
    savings = rec["savings_monthly"]
    verb, color = ("saves", PLANNED_COLOR) if savings >= 0 else ("costs extra", "#f59e0b")
    return (
        f'<div class="os-card"><h4>Recommendation {badge}</h4>'
        f'<p>Current: <b>{rec["current"]}</b> servers fixed<br>'
        f'Planned: <b>{rec["planned_min"]}–{rec["planned_max"]}</b> servers (avg {rec["planned_avg"]:.1f})</p>'
        f'<div class="value" style="font-size:1.6rem;font-weight:700;color:{color};margin-top:.5rem">'
        f'{money(abs(savings))}/month</div>'
        f'<p style="color:#94a3b8">{verb} · {abs(rec["savings_pct"]):.1f}% vs '
        f'{money(rec["current_monthly"])} today</p></div>'
    )


def guardrail_checklist(sr: ServiceResult) -> str:
    """Return HTML for the guardrail checklist."""
    rows = "".join(
        f'<p style="margin:.35rem 0">{RULE_ICONS.get(g["status"], "•")} <b>{html.escape(g["rule"])}</b>'
        f'<br><span style="color:#94a3b8;font-size:.85rem">{html.escape(g["message"])}</span></p>'
        for g in sr.guardrails
    )
    return f'<div class="os-card"><h4>Safety guardrails</h4>{rows}</div>'


def render(result: ScenarioResult) -> None:
    """Draw the Forecast & Plan page."""
    st.title("Forecast & Plan")
    services = [name for name, sr in result.services.items() if not sr.plan.empty]
    if not services:
        st.info("No services with a plan in this scenario.")
        return
    name = st.selectbox("Service", services)
    sr = result.services[name]
    servers = result.scenario.servers
    capacity_rps = float(servers.loc[servers["service"] == name, "capacity_rps"].mean())
    st.caption(f"Last 7 days of actuals, then the next {config.FORECAST_HOURS // 24} days forecast · "
               f"risk setting {config.risk_label(result.risk)}")
    left, right = st.columns([3, 1.3])
    with left:
        st.subheader("Demand vs capacity")
        st.plotly_chart(demand_chart(sr, capacity_rps, result.scenario.events), width="stretch")
        st.subheader("Servers per hour")
        st.plotly_chart(servers_chart(sr), width="stretch")
    with right:
        st.markdown(recommendation_card(sr), unsafe_allow_html=True)
        st.markdown(f'<div class="os-card"><h4>Why</h4><p>{html.escape(sr.explanation)}</p></div>',
                    unsafe_allow_html=True)
        st.markdown(guardrail_checklist(sr), unsafe_allow_html=True)
