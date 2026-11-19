"""Overview page: KPIs, fleet status, alerts and recommendations."""

import html

import plotly.graph_objects as go
import streamlit as st

from engine import config
from engine.pipeline import ScenarioResult
from ui.styles import SEVERITY_COLORS, STATUS_COLORS, chip

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
ACTION_COLORS = {"scale_down": "#22c55e", "schedule": "#22c55e", "scale_up": "#fb923c", "hold": "#38bdf8"}


def money(value: float) -> str:
    """Format a rupee amount like ₹12,345."""
    return f"{config.CURRENCY}{value:,.0f}"


def kpi_tile(label: str, value: str, hint: str) -> str:
    """Return HTML for one KPI tile."""
    return (f'<div class="os-kpi"><div class="label">{html.escape(label)}</div>'
            f'<div class="value">{html.escape(value)}</div><div class="hint">{html.escape(hint)}</div></div>')


def render_kpis(result: ScenarioResult) -> None:
    """Draw the four headline KPI tiles."""
    k = result.kpis
    tiles = [
        ("Monthly cost", money(k["monthly_cost"]), "All servers, current setup"),
        ("Average utilisation", f"{k['avg_util']:.1f}%", "Mean CPU, active servers, last 14 days"),
        ("Waste score", f"{k['waste_score']:.1f}%", f"{k['zombies']} zombie(s), {k['risky']} risky"),
        ("Potential savings", f"{money(k['potential_savings'])}/mo", "Zombies + right-sizing"),
    ]
    for col, (label, value, hint) in zip(st.columns(4), tiles):
        col.markdown(kpi_tile(label, value, hint), unsafe_allow_html=True)


def status_chart(result: ScenarioResult) -> go.Figure:
    """Build a bar chart of server counts per status."""
    counts = result.profile["status"].value_counts()
    statuses = [s for s in STATUS_COLORS if s in counts.index]
    fig = go.Figure(go.Bar(
        x=statuses,
        y=[int(counts[s]) for s in statuses],
        marker_color=[STATUS_COLORS[s] for s in statuses],
        text=[int(counts[s]) for s in statuses],
        textposition="outside",
        hovertemplate="%{x}: %{y} server(s)<extra></extra>",
    ))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=320, margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
                      yaxis_title="Servers", xaxis_title=None)
    return fig


def render_alerts(result: ScenarioResult) -> None:
    """Draw the alerts list, critical first."""
    st.subheader("Alerts")
    alerts = sorted(result.alerts, key=lambda a: SEVERITY_ORDER.get(a["severity"], 9))
    if not alerts:
        st.markdown('<div class="os-alert">No alerts — fleet looks healthy.</div>', unsafe_allow_html=True)
        return
    for a in alerts:
        color = SEVERITY_COLORS.get(a["severity"], "#94a3b8")
        st.markdown(
            f'<div class="os-alert" style="border-left-color:{color}">'
            f'<span class="sev" style="color:{color}">{html.escape(a["severity"])}</span>'
            f'<b>{html.escape(a["service"])}</b> — {html.escape(a["message"])}</div>',
            unsafe_allow_html=True,
        )


def render_recommendations(result: ScenarioResult) -> None:
    """Draw one recommendation card per service."""
    st.subheader("Recommendations")
    for name, sr in result.services.items():
        rec = sr.recommendation
        action = str(rec.get("action", "hold"))
        badge = chip(html.escape(action.replace("_", " ").capitalize()), ACTION_COLORS.get(action, "#f59e0b"))
        st.markdown(
            f'<div class="os-card"><h4>{html.escape(name)} {badge}</h4>'
            f'<p>{html.escape(sr.explanation)}</p></div>',
            unsafe_allow_html=True,
        )


def render(result: ScenarioResult) -> None:
    """Draw the overview page."""
    sc = result.scenario
    st.title(sc.title)
    st.markdown(f'<div class="os-story">{html.escape(sc.story)}</div>', unsafe_allow_html=True)
    render_kpis(result)
    st.write("")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Fleet status")
        st.plotly_chart(status_chart(result), width="stretch")
    with right:
        render_alerts(result)
    render_recommendations(result)
