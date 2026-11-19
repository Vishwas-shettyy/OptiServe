"""Plotly template "optiserve" and a styling helper."""

import plotly.graph_objects as go
import plotly.io as pio

from ui.styles import ACCENT, FONT, GRID, STATUS_COLORS, SURFACE, TEXT, TEXT_2

TEMPLATE = "optiserve"
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
