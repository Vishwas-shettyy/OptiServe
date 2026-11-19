"""Server Graveyard page: tombstones for wasteful servers plus a formal table."""

import html

import pandas as pd
import streamlit as st

from engine.pipeline import ScenarioResult
from ui.overview import money
from ui.styles import STATUS_COLORS, chip

BURIED = ["Zombie", "Wasteful", "Risky"]
EPITAPHS = {"Zombie": "R.I.P.", "Wasteful": "On notice", "Risky": "Do not bury"}
ACTIONS = {
    "Zombie": "Decommission",
    "Wasteful": "Downsize or consolidate",
    "Risky": "Investigate health — do not remove",
    "Hot": "Add capacity",
    "Right-sized": "Keep",
}
COLUMNS = {
    "name": "Server", "service": "Service", "instance_type": "Instance type", "status": "Status",
    "avg_cpu": "Avg CPU %", "p95_cpu": "P95 CPU %", "monthly_cost": "Cost / month",
    "wasted_monthly": "Wasted / month", "reason": "Reason", "action": "Recommended action",
}


def _since(value: pd.Timestamp) -> str:
    """Format the idle-since date, or a dash when the server is not idle."""
    return value.strftime("%d %b %Y") if pd.notna(value) else "—"


def tombstone(row: pd.Series) -> str:
    """Return the HTML for one tombstone."""
    color = STATUS_COLORS[row["status"]]
    return (
        f'<div class="os-stone" title="{html.escape(row["reason"])}" style="border-top: 3px solid {color}">'
        f'<div class="epitaph">{EPITAPHS[row["status"]]}</div>'
        f'<div class="name">{html.escape(row["name"])}</div>'
        f'<div class="meta">{html.escape(row["instance_type"])} · {html.escape(row["service"])}</div>'
        f'<div class="cost">{money(row["wasted_monthly"])}/mo</div>'
        f'<div class="meta">Idle since {_since(row["idle_since"])}</div>'
        f'<div style="margin-top:.5rem">{chip(row["status"], color)}</div></div>'
    )


def graveyard_view(profile: pd.DataFrame) -> None:
    """Draw the night-sky graveyard of Zombie, Wasteful and Risky servers."""
    stones = profile[profile["status"].isin(BURIED)].sort_values("wasted_monthly", ascending=False)
    total = float(stones["wasted_monthly"].sum())
    counts = " · ".join(f"{(stones['status'] == s).sum()} {s.lower()}" for s in BURIED)
    banner = (
        f'<div class="os-banner"><div class="small">Wasted every month</div>'
        f'<div class="big">{money(total)}</div>'
        f'<div class="small">{len(stones)} servers in the yard — {counts}</div></div>'
    )
    body = "".join(tombstone(r) for _, r in stones.iterrows()) or (
        '<div class="meta" style="color:#cbd5e1">The yard is empty — every server is earning its keep.</div>'
    )
    st.markdown(
        f'<div class="os-sky"><div class="os-moon"></div>{banner}<div class="os-yard">{body}</div></div>',
        unsafe_allow_html=True,
    )
    st.caption("Hover a stone to see why it is here.")


def formal_table(profile: pd.DataFrame) -> pd.DataFrame:
    """Return the readable server table with renamed columns."""
    df = profile.assign(action=profile["status"].map(ACTIONS)).sort_values("wasted_monthly", ascending=False)
    df = df[list(COLUMNS)].rename(columns=COLUMNS)
    df["Avg CPU %"] = df["Avg CPU %"].round(1)
    df["P95 CPU %"] = df["P95 CPU %"].round(1)
    df["Cost / month"] = df["Cost / month"].map(money)
    df["Wasted / month"] = df["Wasted / month"].map(money)
    return df.reset_index(drop=True)


def formal_view(profile: pd.DataFrame, key: str) -> None:
    """Draw the formal table of all servers with a CSV download."""
    table = formal_table(profile)
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button(
        "Download as CSV", table.to_csv(index=False).encode("utf-8"),
        file_name=f"optiserve_servers_{key}.csv", mime="text/csv",
    )


def render(result: ScenarioResult) -> None:
    """Draw the Server Graveyard page."""
    st.title("Server Graveyard")
    view = st.radio("View", ["Graveyard view", "Formal view"], horizontal=True, label_visibility="collapsed")
    if view == "Graveyard view":
        graveyard_view(result.profile)
    else:
        formal_view(result.profile, result.scenario.key)
