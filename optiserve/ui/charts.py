"""Plotly template "optiserve", a styling helper and the shared chart builders."""

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from ui.styles import ACCENT, FONT, GRID, STATUS_COLORS, SURFACE, TEXT, TEXT_2, tint

TEMPLATE = "optiserve"
GRID_STRONG = "#CBD5E1"
COLORWAY = [ACCENT, *STATUS_COLORS.values(), TEXT_2]

_axis = dict(gridcolor=GRID, zerolinecolor=GRID, linecolor="#E6E8EF", tickcolor="#E6E8EF",
             tickfont=dict(color=TEXT_2, size=12), title=dict(font=dict(color=TEXT_2, size=12)), automargin=True)

pio.templates[TEMPLATE] = go.layout.Template(layout=go.Layout(
    font=dict(family=FONT, color=TEXT, size=13),
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    colorway=COLORWAY,
    xaxis=_axis,
    yaxis=_axis,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)",
                font=dict(color=TEXT_2, size=12)),
    hovermode="x unified",
    hoverlabel=dict(bgcolor=SURFACE, bordercolor="#E6E8EF", font=dict(family=FONT, color=TEXT, size=12)),
    margin=dict(l=8, r=8, t=8, b=8),
    title=dict(font=dict(size=16, color=TEXT)),
))


def apply_style(fig: go.Figure, height: int = 360) -> go.Figure:
    """Apply the optiserve template and a fixed height to a figure."""
    fig.update_layout(template=TEMPLATE, height=height)
    return fig


# ---- shared colours ---------------------------------------------------------

ACTUAL_COLOR = "#334155"
EXPECTED_COLOR = ACCENT
CURRENT_COLOR = "#64748B"
PLANNED_COLOR = STATUS_COLORS["Right-sized"]
EVENT_COLOR = STATUS_COLORS["Hot"]


def layout(fig: go.Figure, height: int, y_title: str = "") -> go.Figure:
    """Apply the optiserve style, a height and a y-axis title."""
    apply_style(fig, height)
    fig.update_layout(yaxis_title=y_title, margin=dict(l=8, r=8, t=36, b=8))
    return fig


def fleet_status_bar(counts: dict[str, int]) -> go.Figure:
    """Build a single horizontal stacked bar of server counts by status."""
    fig = go.Figure()
    for status, color in STATUS_COLORS.items():
        n = int(counts.get(status, 0))
        if n == 0:
            continue
        fig.add_trace(go.Bar(y=["Fleet"], x=[n], name=f"{status} ({n})", orientation="h", marker_color=color,
                             marker_line=dict(color=SURFACE, width=2), text=[str(n)], textposition="inside",
                             insidetextanchor="middle", textfont=dict(color="#FFFFFF", size=13),
                             hovertemplate=f"{status}: {n} server(s)<extra></extra>"))
    fig.update_layout(barmode="stack", hovermode="closest", bargap=0.25)
    fig.update_yaxes(visible=False)
    fig.update_xaxes(title_text="Servers", dtick=1 if sum(counts.values()) <= 20 else None, showgrid=False)
    return layout(fig, 170)


def demand_chart(history: pd.DataFrame, forecast: pd.DataFrame, plan: pd.DataFrame, events: pd.DataFrame,
                 capacity_rps: float) -> go.Figure:
    """Build the demand chart: actual, expected, likely range, current and planned capacity, events."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=forecast["timestamp"], y=forecast["high"], line=dict(width=0), showlegend=False,
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=forecast["timestamp"], y=forecast["low"], line=dict(width=0), fill="tonexty",
                             fillcolor=tint(ACCENT, .14), name="Likely range", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=history["timestamp"], y=history["requests"], name="Actual",
                             line=dict(color=ACTUAL_COLOR, width=1.6), hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=forecast["timestamp"], y=forecast["expected"], name="Expected",
                             line=dict(color=EXPECTED_COLOR, width=2), hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=plan["timestamp"], y=plan["current"] * capacity_rps, name="Current capacity",
                             line=dict(color=CURRENT_COLOR, dash="dash", width=1.5, shape="hv"),
                             hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=plan["timestamp"], y=plan["planned"] * capacity_rps, name="Planned capacity",
                             line=dict(color=PLANNED_COLOR, width=2, shape="hv"), hovertemplate="%{y:,.0f}"))
    start, end = history["timestamp"].min(), forecast["timestamp"].max() + pd.Timedelta(hours=1)
    for ev in events.itertuples():
        if ev.end < start or ev.start > end:
            continue
        x0, x1 = max(ev.start, start), min(ev.end + pd.Timedelta(hours=1), end)
        late = (x0 - start) > (end - start) * 0.7
        fig.add_vrect(x0=x0, x1=x1, fillcolor=tint(EVENT_COLOR, .12), line_width=0, layer="below",
                      annotation_text=ev.label, annotation_position="top right" if late else "top left",
                      annotation_font=dict(color=EVENT_COLOR, size=11))
    split = forecast["timestamp"].min()
    fig.add_vline(x=split, line=dict(color=GRID_STRONG, dash="dot", width=1))
    fig.add_annotation(x=split, y=0.99, yref="paper", text="Forecast →", showarrow=False, xanchor="left",
                       yanchor="top", xshift=4, font=dict(color=TEXT_2, size=11))
    fig.update_yaxes(rangemode="tozero", tickformat=",")
    layout(fig, 420, "Requests per hour")
    fig.update_layout(margin=dict(l=8, r=8, t=72, b=8))
    return fig


def servers_chart(plan: pd.DataFrame) -> go.Figure:
    """Build the servers-per-hour chart: current fixed vs planned."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=plan["timestamp"], y=plan["current"], name="Current servers",
                             line=dict(color=CURRENT_COLOR, dash="dash", width=1.5, shape="hv")))
    fig.add_trace(go.Scatter(x=plan["timestamp"], y=plan["planned"], name="Planned servers",
                             line=dict(color=PLANNED_COLOR, width=2, shape="hv"),
                             fill="tozeroy", fillcolor=tint(PLANNED_COLOR, .10)))
    fig.update_yaxes(rangemode="tozero")
    return layout(fig, 260, "Servers")


SHORT_COLOR = STATUS_COLORS["Risky"]


def test_week_chart(series: pd.DataFrame) -> go.Figure:
    """Build the test-week chart: actual demand, fixed and OptiServe capacity, hours short shaded red."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series["timestamp"], y=series["capacity_fixed"], name="Fixed capacity",
                             line=dict(color=CURRENT_COLOR, dash="dash", width=1.5, shape="hv"),
                             hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=series["timestamp"], y=series["capacity_plan"], name="OptiServe capacity",
                             line=dict(color=PLANNED_COLOR, width=2, shape="hv"), hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=series["timestamp"], y=series["actual"], name="Actual demand",
                             line=dict(color=ACTUAL_COLOR, width=1.6), hovertemplate="%{y:,.0f}"))
    short = series[(series["actual"] > series["capacity_fixed"]) | (series["actual"] > series["capacity_plan"])]
    if not short.empty:
        fig.add_trace(go.Scatter(x=short["timestamp"], y=short["actual"], mode="markers", name="Hours short",
                                 marker=dict(color=SHORT_COLOR, size=7), hovertemplate="Short: %{y:,.0f}"))
        for ts in short["timestamp"]:
            fig.add_vrect(x0=ts, x1=ts + pd.Timedelta(hours=1), fillcolor=tint(SHORT_COLOR, .15), line_width=0,
                          layer="below")
    fig.update_yaxes(rangemode="tozero", tickformat=",")
    return layout(fig, 380, "Requests per hour")


def fleet_capacity_chart(actual: pd.DataFrame, forecast: pd.DataFrame) -> go.Figure:
    """Build the fleet-wide chart: actual + expected demand vs current and planned capacity.

    `actual` has timestamp, requests; `forecast` has timestamp, expected, current_cap, planned_cap.
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=actual["timestamp"], y=actual["requests"], name="Actual demand",
                             line=dict(color=ACTUAL_COLOR, width=1.6), hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=forecast["timestamp"], y=forecast["expected"], name="Expected demand",
                             line=dict(color=EXPECTED_COLOR, width=2), fill="tozeroy",
                             fillcolor=tint(ACCENT, .08), hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=forecast["timestamp"], y=forecast["current_cap"], name="Current capacity",
                             line=dict(color=CURRENT_COLOR, dash="dash", width=1.5, shape="hv"),
                             hovertemplate="%{y:,.0f}"))
    fig.add_trace(go.Scatter(x=forecast["timestamp"], y=forecast["planned_cap"], name="Planned capacity",
                             line=dict(color=PLANNED_COLOR, width=2, shape="hv"), hovertemplate="%{y:,.0f}"))
    if not forecast.empty:
        split = forecast["timestamp"].min()
        fig.add_vline(x=split, line=dict(color=GRID_STRONG, dash="dot", width=1))
        fig.add_annotation(x=split, y=0.99, yref="paper", text="Forecast →", showarrow=False, xanchor="left",
                           yanchor="top", xshift=4, font=dict(color=TEXT_2, size=11))
    fig.update_yaxes(rangemode="tozero", tickformat=",")
    layout(fig, 340, "Requests per hour")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=8, r=8, t=40, b=8))
    return fig
